FROM node:22-slim
RUN npm install -g vitest@2 @playwright/test@1
WORKDIR /app
