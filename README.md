# Meet Halfway

Friends enter where they are and get a fair meeting point with cafés nearby.

A location-based web app built with Django, PostGIS and Leaflet. It finds the middle point of a
group of friends, shows each person's line to it and the area the group covers, lists cafés
within 300 m and gives a fairness score based on how evenly the distances are spread.

## Tech stack

- **Database:** PostgreSQL 16 + PostGIS 3.4, managed with pgAdmin 4
- **Back end:** Python 3.12, Django 5.2 (GeoDjango)
- **Front end:** Bootstrap 5.3, Leaflet 1.9.4, OpenStreetMap
- **Deployment:** Docker Compose on a private network

## Running it

Docker Desktop is required.

```bash
cp .env.example .env                                # then set your own passwords and secret key
docker compose up --build                           # start the containers
docker compose exec web python manage.py migrate    # in a second terminal: create the tables
```

- App: http://localhost:8000
- pgAdmin: http://localhost:5050. Register a server with host `db`, port `5432` and the
  `POSTGRES_` values from `.env`.

To stop, run `docker compose down`. Adding `-v` also deletes the database.

