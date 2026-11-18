# syntax=docker/dockerfile:1

# Dev image for the Vite server. Vite 8 needs Node 20.19+ or 22.12+.
# Debian-based (not alpine) so Vite's native bindings install without surprises.
FROM node:22-slim

WORKDIR /app

# Dependencies first so this layer is cached until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# Vite binds to localhost by default, which is unreachable from outside the
# container. --host 0.0.0.0 makes it listen on all interfaces.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
