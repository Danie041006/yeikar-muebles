# ── Stage 1: build de producción ─────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar manifiestos primero para aprovechar el caché de capas
COPY package*.json ./
RUN npm ci --frozen-lockfile

# Copiar el resto del código y construir
COPY . .
RUN npm run build

# ── Stage 2: servidor nginx con los estáticos ─────────────────────────────
FROM nginx:alpine

# Eliminar config default de nginx
RUN rm /etc/nginx/conf.d/default.conf

# Copiar configuración personalizada
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Copiar resultado del build
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]