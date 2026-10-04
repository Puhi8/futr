# Futr

Futr is a web app for managing / ordering Lopolis meals.

## Compose setup

```yaml
services:
  futr:
    image: ghcr.io/puhi8/futr:latest
    restart: unless-stopped
    ports:
      - "5847:5847"
    volumes:
      - futr-data:/data

volumes:
  futr-data:
```

Credentials and meal preferences are stored in `/data` as `creds.json` and `meals.json`.

## Run Locally

### Requirements for local running

- Python 3.13+
- Node.js 22+
- `curl` available on the system

### Running

1. Build the frontend:

```sh
cd Frontend
npm i
npm run build
cd ..
```

2. Start the Python server:

```sh
python app.py
```

3. Open the app at:

```text
http://localhost:5847
```

The app stores local data in `creds.json` and `meals.json` by default. Set `DATA_DIR` to store them somewhere else.

