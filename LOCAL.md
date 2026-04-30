# Local Development

To set up a local development environment for Policy Atlas, follow these steps:

1. Ensure you have Docker installed and running on your machine.
2. Clone the Policy Atlas repository to your local machine.
3. Run docker-compose from the root of the repository to start the local development environment:

```bash
docker-compose -f docker-compose.yml up
```

4. This will start the necessary dependent services, such as the database and the connection layers (such as pg-meta)
5. Set the environment variables for local development - these can be found in the `docker-compose.yml`.
6. Run the backend and frontend services natively - feel free to use any hot reload commands as needed:

```bash
cd backend && uv run python main.py
cd frontend && npm run dev
```