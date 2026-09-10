# Frontend Fargate deployment

The Next.js UI is deployed independently as stack
`astra-interior-designer-frontend`. It reuses the backend stack's VPC, public
subnets, ECS cluster, and Application Load Balancer, but owns its ECS service,
task definition, target group, CloudFront distribution, IAM roles, security
group, and CloudWatch log group.

The browser calls the UI's same-origin `/api/astra/*` routes. The Next.js server
then calls the backend at `ASTRA_API_URL` and reads `APP_API_KEY` from the
existing backend secret into `ASTRA_API_KEY`. The credential is never built into
or sent to browser JavaScript. Browser uploads and GLB downloads continue to use
presigned S3 URLs directly.

## Build and deploy

Run from the repository root with Docker and an authenticated AWS CLI session:

```sh
ASTRA_WEB_ECR=022104542793.dkr.ecr.us-east-1.amazonaws.com/astra-interior-designer-web
ASTRA_WEB_TAG="release-$(date -u +%Y%m%dT%H%M%SZ)"

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${ASTRA_WEB_ECR%/*}"
docker build --platform linux/arm64 \
  --build-arg NEXT_PUBLIC_ASTRA_BACKEND_ENABLED=true \
  -t "$ASTRA_WEB_ECR:$ASTRA_WEB_TAG" web
docker push "$ASTRA_WEB_ECR:$ASTRA_WEB_TAG"

ASTRA_WEB_DIGEST="$(aws ecr describe-images --region us-east-1 \
  --repository-name astra-interior-designer-web \
  --image-ids "imageTag=$ASTRA_WEB_TAG" \
  --query 'imageDetails[0].imageDigest' --output text)"
ASTRA_WEB_ORIGIN_SECRET="$(openssl rand -base64 48 | tr -d '=+/')"

aws cloudformation deploy --region us-east-1 \
  --stack-name astra-interior-designer-frontend \
  --template-file infra/deployment/frontend-fargate.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    "ImageUri=$ASTRA_WEB_ECR@$ASTRA_WEB_DIGEST" \
    "OriginSecret=$ASTRA_WEB_ORIGIN_SECRET"
```

Use a fresh immutable tag for each image and deploy its digest. On later stack
updates, omit `OriginSecret` so CloudFormation preserves the existing value.

After the first deployment, add the `WebUrl` output to the S3 bucket's allowed
CORS origins. Preserve the localhost origins used for development.

## Verification

Read the deployment outputs and wait for the service to stabilize:

```sh
aws cloudformation describe-stacks --region us-east-1 \
  --stack-name astra-interior-designer-frontend \
  --query 'Stacks[0].Outputs'
aws ecs wait services-stable --region us-east-1 \
  --cluster astra-interior-designer \
  --services astra-interior-designer-web
```

CloudWatch logs are in `/astra-interior-designer/frontend`. The public
CloudFront URL should return `200` for `/` and `/api/health`. The authenticated
proxy should return the backend session list from `/api/astra/sessions` and
preserve the message endpoint's SSE stream.
