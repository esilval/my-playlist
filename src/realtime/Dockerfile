# Imagen del servicio de tiempo real (C6, ADR-0005): se compila con tsc y la imagen
# final solo lleva las dependencias de ejecución.
FROM node:22-alpine AS build
WORKDIR /realtime
# Sin package-lock.json en el repositorio: las versiones salen de los rangos de package.json.
COPY package.json ./
RUN npm install
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine
WORKDIR /realtime
ENV NODE_ENV=production
COPY package.json ./
RUN npm install --omit=dev
COPY --from=build /realtime/dist ./dist
USER node
EXPOSE 3001
CMD ["node", "dist/server.js"]
