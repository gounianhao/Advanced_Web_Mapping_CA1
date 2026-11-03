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

## How the meeting point is found

All the spatial work is done in PostGIS, in `meetups/services/spatial.py`:

- **Meeting point:** `ST_Centroid(ST_Collect(...))` of the friends, calculated in Irish Transverse Mercator (EPSG:2157) so it is in metres
- **Lines and distances:** `ST_MakeLine` from each friend to the point and `ST_Length` on geography for metres
- **Group area:** `ST_ConvexHull` of the friends, `ST_Area` for its size and `ST_Contains` to count the venues inside
- **Venues nearby:** `ST_DWithin` on geography within the radius (300 m by default), nearest first, plus the `ST_Buffer` circle that was searched. If nothing is in range, the 5 nearest are found with the KNN operator `<->`
- **Fairness score:** `100 × (1 − standard deviation / mean distance)`, from 0 to 100: Fair (75+), OK (50+) or Unfair. The venues can also be ranked by the same score

Venue searches use a GiST index on `location::geography`.

## API

Interactive docs: http://localhost:8000/api/docs/. To try the endpoints that need a login, log in at
http://localhost:8000/api-auth/login/ first.

- `GET /api/venues/` returns all venues as GeoJSON (public). Filters: `?in_bbox=minLon,minLat,maxLon,maxLat`, `?category=cafe`
- `GET/POST /api/groups/`, `GET/PATCH/DELETE /api/groups/{id}/` manage your own groups
- `GET/POST /api/friends/?group={id}`, `PATCH/DELETE /api/friends/{id}/` manage friends; the meeting point updates straight away
- `POST /api/groups/{id}/compute/` returns the meeting point, lines, group area, fairness score and venues nearby
- `GET /api/groups/{id}/venues/?radius=300&category=cafe` lists venues around the meeting point
- `GET /api/groups/{id}/fair-venues/` lists the same venues, fairest first
- `GET /api/geocode/?q=Heuston Station` searches for an address in Dublin (OpenStreetMap Nominatim)

Friend locations are GeoJSON points, e.g. `{"type": "Point", "coordinates": [-6.2546, 53.3438]}`, and must be in
Greater Dublin. A group needs 2 to 15 friends and a radius of 50 to 2000 m.

## Tests

```bash
docker compose exec web pytest
```
