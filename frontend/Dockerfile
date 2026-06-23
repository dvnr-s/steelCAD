# SteelCAD Frontend — multi-stage build
# Stage 1 builds the Vite bundle; stage 2 serves it with nginx and proxies the API.

# ─── Build stage ─────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm ci

# Build the production bundle
COPY . .
RUN npm run build

# ─── Serve stage ─────────────────────────────────────────
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
