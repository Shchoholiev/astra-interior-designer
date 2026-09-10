# Fargate deployment

Public API: **https://d895b1qs2o034.cloudfront.net** (the stack's `ApiUrl` output).
Account `022104542793`, region `us-east-1`, stack `astra-interior-designer-backend`.
The backend runs as one ECS Fargate task: Linux x86_64, 0.5 vCPU, 1 GiB, one Uvicorn worker on port 8000.

## Build and push

Run from the repository root with Docker, uv, the project virtual environment, and an authenticated AWS deployment profile.
The staging helper uses the SDK commit in `uv.lock`; its local checkout must be available in the uv cache or supplied with `--sdk-source`.
Only application sources, package metadata, the locked SDK wheel, and the explicit Dockerfile enter the build context.

```sh
ASTRA_BUILD_CONTEXT="$(.venv/bin/python infra/deployment/prepare_backend_build.py --dockerfile)"
ASTRA_ECR=022104542793.dkr.ecr.us-east-1.amazonaws.com/astra-interior-designer-backend
ASTRA_IMAGE_TAG="release-$(date -u +%Y%m%dT%H%M%SZ)"
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${ASTRA_ECR%/*}"
docker build --platform linux/amd64 -t "$ASTRA_ECR:$ASTRA_IMAGE_TAG" "$ASTRA_BUILD_CONTEXT"
docker push "$ASTRA_ECR:$ASTRA_IMAGE_TAG"
ASTRA_DIGEST="$(aws ecr describe-images --region us-east-1 --repository-name astra-interior-designer-backend --image-ids "imageTag=$ASTRA_IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text)"
aws cloudformation deploy --region us-east-1 --stack-name astra-interior-designer-backend \
  --template-file infra/deployment/fargate.yaml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "ImageUri=$ASTRA_ECR@$ASTRA_DIGEST"
```

Use a fresh immutable tag for each build and deploy its digest. The command above preserves existing stack parameters.
Initial stack creation also requires `OriginSecret`: securely supply a random 32–128 character value using letters, digits, `_`, or `-`.

## Configuration and ownership

The stack owns only this application's VPC, ALB, CloudFront distribution, ECS resources, IAM task/execution roles, and logs.
The existing ECR repository, S3 bucket, DynamoDB tables, backend secret, and sandbox S3 role remain external resources.
Add the stack's `TaskRoleArn` to the existing `astra-interior-designer-sandbox-s3` role's trust policy before creating sessions.
The task role reads `astra-interior-designer/backend` through `AWS_SECRET_ID`; do not inject `AWS_PROFILE` or static AWS access keys.
The secret contains `OPENAI_API_KEY`, `APP_API_KEY`, `S3_SIGNING_ACCESS_KEY_ID`, and `S3_SIGNING_SECRET_ACCESS_KEY`.
ECS also injects `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` from that secret using the execution role.
The dedicated S3 signing credentials must cover the full 12-hour scene and image
URL lifetime. The external sandbox role must allow `GetObject` and `PutObject`
for `sandboxes/*/render.png`, as well as the existing scene permissions. Its
session policy restricts these permissions to one session. The signing identity
must allow `GetObject` for that render key pattern; the stack's backend task role
also needs it to read image metadata. Deploy the updated task role with the API.
Apply the additive render policies to the existing external identities using the
deployment AWS profile; their existing input and scene policies remain in place:

```sh
aws iam put-role-policy --role-name astra-interior-designer-sandbox-s3 \
  --policy-name astra-render-delivery \
  --policy-document file://infra/deployment/render-sandbox-policy.json
aws iam put-user-policy --user-name astra-interior-designer-s3-signer \
  --policy-name astra-render-delivery \
  --policy-document file://infra/deployment/render-signing-policy.json
```

`CORS_ORIGINS` allows `http://localhost:3000` and `http://localhost:5173`; update the task definition when frontend origins change.

## Runtime and verification

Build the Blender sandbox image with `.venv-modal/bin/python infra/runtime/image.py`; add `--publish` after validation to publish `astra-blender:v6`. The deployment template and backend defaults select this version, which includes PNG delivery, upload receipts, and the seven-skill Interior Design plugin with viewer-camera exports. New agent sessions register the baked plugin directory as a capability directory. Existing sandboxes need replacement to pick up the new plugin.
The Fargate application creates Modal sandboxes from that image and uses the `astra-openai-executor` Modal secret for their executor credential.
New sandboxes download their session's S3 inputs in the background. The supervisor owns `/workspace/inputs`; Blender and the executor run as `astra-agent` and can only read those files. Attachment delivery is confirmed before submitting a message. Existing v1 sandboxes retain their original background polling and writable inputs until replaced; they do not support the pre-message sync command.
`GET /health` is unauthenticated and returns `{"status":"ok"}`; `/sessions` routes require the application Bearer token.
Read deployment outputs with `aws cloudformation describe-stacks --region us-east-1 --stack-name astra-interior-designer-backend --query 'Stacks[0].Outputs'`.
CloudWatch logs are in `/astra-interior-designer/backend`.
CloudFront provides public HTTPS; its restricted ALB origin uses HTTP. Caching is disabled and Authorization/CORS headers are forwarded.
CloudFront waits up to 120 seconds for the first response or between packets. SSE emits a keep-alive every 15 seconds, and no response-completion cap is configured.
Session creation still waits for sandbox readiness before responding, so cold provisioning exceeding 120 seconds can produce a CloudFront timeout.
