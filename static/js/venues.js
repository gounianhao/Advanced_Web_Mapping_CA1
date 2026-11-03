/*
 * Meet Halfway - venue layer.
 *
 * Loads only the venues inside the visible part of the map from
 * GET /api/venues/?in_bbox=..., reloads them when the map is moved, and
 * groups nearby markers into clusters when zoomed out.
 */
(function () {
  "use strict";

  const map = window.MeetHalfway.map;
  const config = window.MeetHalfway.config;
  const statusEl = document.getElementById("venue-status");

  // Marker colours come from the CSS variables, so the map and the legend always match.
  const css = getComputedStyle(document.documentElement);
  const COLOURS = {
    cafe: css.getPropertyValue("--venue-cafe").trim(),
    restaurant: css.getPropertyValue("--venue-restaurant").trim(),
    pub: css.getPropertyValue("--venue-pub").trim(),
  };

  const clusters = L.markerClusterGroup({
    chunkedLoading: true,        // add markers in small batches so the page never freezes
    showCoverageOnHover: false,
    maxClusterRadius: 45,
    disableClusteringAtZoom: 17, // show every venue when zoomed right in
  });
  map.addLayer(clusters);

  let loadedBounds = null; // area covered by the last successful request
  let request = null;      // the request in progress, so it can be cancelled
  let moveTimer = null;

  function setStatus(text) {
    statusEl.textContent = text;
  }

  /** Popup content built with DOM methods (textContent), so venue names can't inject HTML. */
  function popupContent(props) {
    const box = document.createElement("div");
    box.className = "venue-popup";

    const title = document.createElement("strong");
    title.textContent = props.name;
    box.append(title);

    const kind = document.createElement("div");
    kind.className = "text-body-secondary";
    kind.textContent = props.cuisine ? `${props.category_label} · ${props.cuisine}` : props.category_label;
    box.append(kind);

    for (const [icon, text] of [["bi-geo-alt", props.address], ["bi-clock", props.opening_hours]]) {
      if (!text) continue;
      const line = document.createElement("div");
      const i = document.createElement("i");
      i.className = `bi ${icon} me-1`;
      i.setAttribute("aria-hidden", "true");
      line.append(i, document.createTextNode(text));
      box.append(line);
    }

    if (props.website && /^https?:\/\//i.test(props.website)) {
      const link = document.createElement("a");
      link.href = props.website;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Website";
      box.append(link);
    }
    return box;
  }

  function toMarker(feature) {
    const [lon, lat] = feature.geometry.coordinates; // GeoJSON order is [longitude, latitude]
    const props = feature.properties;
    const marker = L.circleMarker([lat, lon], {
      radius: 7,
      color: "#ffffff",
      weight: 1.5,
      fillColor: COLOURS[props.category] || "#6c757d",
      fillOpacity: 0.95,
    });
    marker.bindPopup(() => popupContent(props)); // built only when the popup is opened
    return marker;
  }

  async function loadVenues() {
    const view = map.getBounds();
    // Nothing to do if the last request already covered this view.
    if (loadedBounds && loadedBounds.contains(view)) return;

    // Ask for a slightly bigger area so small pans don't need a new request.
    const area = view.pad(0.25);
    const bbox = [area.getWest(), area.getSouth(), area.getEast(), area.getNorth()]
      .map((n) => n.toFixed(5))
      .join(",");

    if (request) request.abort();
    request = new AbortController();
    setStatus("Loading venues…");

    try {
      const response = await fetch(`${config.venuesUrl}?in_bbox=${bbox}`, {
        headers: { Accept: "application/json" },
        signal: request.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      clusters.clearLayers();
      clusters.addLayers(data.features.map(toMarker));
      loadedBounds = area;

      const count = data.features.length;
      setStatus(count === 0 ? "No venues in this area." : `${count.toLocaleString()} venues in this area.`);
    } catch (error) {
      if (error.name === "AbortError") return; // replaced by a newer request
      console.error("Could not load venues:", error);
      setStatus("Could not load venues. Move the map to try again.");
    }
  }

  // Wait until the map stops moving before loading (avoids a request per frame).
  map.on("moveend", () => {
    clearTimeout(moveTimer);
    moveTimer = setTimeout(loadVenues, 250);
  });

  loadVenues();
})();
