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
cp .env.example .env                                    # then set your own passwords and secret key
docker compose up --build

# in a second terminal:
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_venues    # OpenStreetMap venues
docker compose exec web python manage.py seed_demo      # demo user: demo / meethalfway-demo
```

- App: http://localhost:8000 (admin at `/admin/`)
- pgAdmin: http://localhost:5050 (server host `db`, port `5432`)

## Data

About 2,900 cafés, restaurants and pubs in Greater Dublin from OpenStreetMap, saved in
`data/dublin_venues.geojson`. Run `manage.py fetch_venues` to download them again.

## API

- `GET /api/venues/` returns all venues as GeoJSON
- `GET /api/venues/?in_bbox=minLon,minLat,maxLon,maxLat` returns only the venues in an area
- `GET /api/venues/?category=cafe` filters by `cafe`, `restaurant` or `pub`
