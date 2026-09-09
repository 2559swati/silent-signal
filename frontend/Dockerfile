# Phase 15 multi-stage frontend image.
#
# Stage 1 (build): install dependencies and produce the static bundle with
# the project's own build script (`tsc -b && vite build`). VITE_API_URL is
# baked in at build time by Vite, so it arrives as a build ARG (Compose
# passes http://localhost:8000, reachable from host browsers).
# Stage 2 (serve): nginx serves only the built static files -- no Node,
# no dev dependencies in the final image.

FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Optional: bake a remote backend URL into the bundle. Empty (default)
# means same-origin /api/*, served by the nginx proxy in this image.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
