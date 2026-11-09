# Candidate image recipe only: building does not confer deployment admission.
FROM node:22.23.2-bookworm-slim@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9
WORKDIR /opt/dial-project-admin
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force
COPY server.mjs admission.mjs health.mjs ./
ENV NODE_ENV=production NODE_OPTIONS=--max-old-space-size=128
USER node
EXPOSE 9090
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD ["node", "health.mjs"]
CMD ["node", "server.mjs"]
