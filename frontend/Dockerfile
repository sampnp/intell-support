FROM node:20-alpine

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# Vite dev server (hot reload); `npm run build` is run separately as a check.
CMD ["npm", "run", "dev"]
