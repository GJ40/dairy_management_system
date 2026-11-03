# ==============================================================================
# Multi-stage Dockerfile for Dairy Management System React Frontend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build production bundle with Node.js
# ------------------------------------------------------------------------------
FROM node:24-alpine AS builder

WORKDIR /app

# Copy dependency specifications first for optimal layer caching
COPY package.json package-lock.json ./

# Install exact dependencies from package-lock.json
RUN npm ci

# Support build-time configuration of the API Base URL and session cookies
# Defaults to relative `/api/v1` so requests route through the Nginx reverse proxy
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_SESSION_HINT_COOKIE=dairy_session
ARG VITE_CUSTOMER_SESSION_HINT_COOKIE=dairy_customer_session

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SESSION_HINT_COOKIE=$VITE_SESSION_HINT_COOKIE \
    VITE_CUSTOMER_SESSION_HINT_COOKIE=$VITE_CUSTOMER_SESSION_HINT_COOKIE

# Copy application source files and configurations
COPY public/ ./public/
COPY src/ ./src/
COPY index.html ./
COPY vite.config.js ./
COPY eslint.config.js ./

# Build production bundle into /app/dist
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Serve production bundle with Alpine Nginx
# ------------------------------------------------------------------------------
FROM nginx:alpine AS runner

# Remove default Nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx configuration supporting SPA routing and /api/ reverse proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose web server HTTP port
EXPOSE 80

# Start Nginx in foreground mode
CMD ["nginx", "-g", "daemon off;"]

