server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    # Serve static files collected into the shared static volume
    location /static/ {
        alias /usr/share/nginx/html/static/;
        access_log off;
        expires 7d;
    }

    # Proxy all other requests to the Django app (Gunicorn)
    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://web:8000;
        proxy_read_timeout 120;
        proxy_connect_timeout 10;
    }
}