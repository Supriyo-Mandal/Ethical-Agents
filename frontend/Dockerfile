FROM node:20-alpine

WORKDIR /app

# Copy frontend package files
COPY frontend/package.json ./frontend/package.json

RUN npm install --prefix frontend

# Copy the frontend source
COPY frontend ./frontend

WORKDIR /app/frontend

ENV VITE_API_URL=http://localhost:8000

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]