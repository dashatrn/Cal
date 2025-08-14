FROM node:20-alpine

WORKDIR /usr/src/app

COPY package*.json ./
RUN npm ci

COPY . .
ENV HOST=0.0.0.0
EXPOSE 5173
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]