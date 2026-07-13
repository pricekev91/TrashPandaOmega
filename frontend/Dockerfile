FROM nginx:1.29-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/app.js /usr/share/nginx/html/app.js
COPY frontend/feeds.html /usr/share/nginx/html/feeds.html
COPY frontend/feeds.js /usr/share/nginx/html/feeds.js
COPY frontend/styles.css /usr/share/nginx/html/styles.css