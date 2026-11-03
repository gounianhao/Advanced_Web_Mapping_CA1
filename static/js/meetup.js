/*
 * Meet Halfway - group planner (only loaded for logged-in users).
 *
 * Pick or create a group, add friends (address search, a click on the map or
 * the browser's location) and drag them around. Every change is sent to the
 * REST API, which asks PostGIS for the meeting point, each friend's line to
 * it, the group's area, the search circle, the fairness score and places to
 * meet. This script then draws the answer on the map and in the sidebar.
 *
 * Everything shown on the page is built with DOM methods and textContent, so
 * names typed by users can never inject HTML.
 */
(function () {
  "use strict";

  const { map, config } = window.MeetHalfway;
  const $ = (id) => document.getElementById(id);

  const STORAGE_KEY = "meethalfway:group";
  const FRIEND_COLOURS = [
    "#c2185b", "#1565c0", "#2e7d32", "#ef6c00", "#6a1b9a", "#00838f", "#ad1457", "#4e342e",
    "#283593", "#558b2f", "#d84315", "#00695c", "#5d4037", "#37474f", "#827717",
  ];
  const CATEGORY_NAMES = {
    cafe: ["café", "cafés"],
    restaurant: ["restaurant", "restaurants"],
    pub: ["pub", "pubs"],
  };
  const FAIRNESS_COLOURS = { Fair: "bg-success", OK: "bg-warning", Unfair: "bg-danger" };
  const SMALL_SCREEN = window.matchMedia("(max-width: 991.98px)");

  const els = {
    sidebar: $("sidebar"),
    alert: $("app-alert"),
    alertText: $("app-alert-text"),
    alertClose: $("app-alert-close"),
    groupPicker: $("group-picker"),
    groupSelect: $("group-select"),
    groupDelete: $("group-delete"),
    groupForm: $("group-form"),
    groupName: $("group-name"),
    groupPanel: $("group-panel"),
    friendList: $("friend-list"),
    friendCount: $("friend-count"),
    friendsEmpty: $("friends-empty"),
    friendForm: $("friend-form"),
    friendName: $("friend-name"),
    friendAddress: $("friend-address"),
    addressSearch: $("address-search"),
    addressResults: $("address-results"),
    pickOnMap: $("pick-on-map"),
    useLocation: $("use-location"),
    mapHint: $("map-hint"),
    busy: $("busy"),
    fairnessText: $("fairness-text"),
    fairnessMeter: $("fairness-meter"),
    fairnessBar: $("fairness-bar"),
    resultStats: $("result-stats"),
    radius: $("radius"),
    radiusValue: $("radius-value"),
    category: $("category"),
    fallbackNote: $("fallback-note"),
    venueEmpty: $("venue-empty"),
    venueList: $("venue-list"),
  };

  const state = {
    groups: [],
    group: null,   // the selected group as the API returns it, including its friends
    area: null,    // { area_m2, venues_inside } from the last calculation
    venues: null,  // the last venue search: search_area, fallback, venues (GeoJSON)...
    sort: "nearest",
    picking: false,
    run: 0,        // answers to requests that a newer request has replaced are ignored
  };

  // ---------------------------------------------------------------------------
  // Map layers
  // ---------------------------------------------------------------------------
  // The group area and the search circle sit below the lines and markers.
  map.createPane("areas");
  map.getPane("areas").style.zIndex = 350;

  const layers = {
    hull: L.layerGroup().addTo(map),
    searchArea: L.layerGroup().addTo(map),
    lines: L.layerGroup().addTo(map),
    places: L.layerGroup().addTo(map),
    friends: L.layerGroup().addTo(map),
    meeting: L.layerGroup().addTo(map),
  };
  const friendMarkers = new Map(); // friend id -> marker

  const overlays = {
    "Lines to the meeting point": layers.lines,
    "Group area": layers.hull,
    "Search area": layers.searchArea,
    "Places to meet": layers.places,
  };
  if (window.MeetHalfway.venueLayer) overlays["All venues"] = window.MeetHalfway.venueLayer;
  L.control.layers(null, overlays, { position: "topright" }).addTo(map);

  // ---------------------------------------------------------------------------
  // Small helpers
  // ---------------------------------------------------------------------------
  function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  }

  function icon(name) {
    const i = el("i", `bi ${name}`);
    i.setAttribute("aria-hidden", "true");
    return i;
  }

  function formatDistance(metres) {
    if (metres === null || metres === undefined) return "";
    if (metres < 1000) return `${Math.round(metres)} m`;
    return `${(metres / 1000).toFixed(metres < 10000 ? 1 : 0)} km`;
  }

  function formatArea(squareMetres) {
    if (squareMetres >= 10000) return `${(squareMetres / 1e6).toFixed(2)} km²`;
    return `${Math.round(squareMetres)} m²`;
  }

  function plural(category, count) {
    const [one, many] = CATEGORY_NAMES[category] || [category, `${category}s`];
    return count === 1 ? one : many;
  }

  function initials(name) {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  }

  const colourOf = (index) => FRIEND_COLOURS[index % FRIEND_COLOURS.length];
  const latLng = (point) => [point.coordinates[1], point.coordinates[0]]; // GeoJSON is [lon, lat]
  const geoPoint = (lat, lng) => ({ type: "Point", coordinates: [Number(lng.toFixed(6)), Number(lat.toFixed(6))] });
  const groupUrl = (id) => `${config.urls.groups}${id}/`;
  const friendUrl = (id) => `${config.urls.friends}${id}/`;

  function searchQuery() {
    return new URLSearchParams({ radius: els.radius.value, category: els.category.value }).toString();
  }

  function closeSidebarOnSmallScreens() {
    if (SMALL_SCREEN.matches && window.bootstrap) {
      window.bootstrap.Offcanvas.getOrCreateInstance(els.sidebar).hide();
    }
  }

  function flyToMarker(marker, zoom) {
    closeSidebarOnSmallScreens();
    map.once("moveend", () => marker.openPopup());
    map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), zoom));
  }

  // ---------------------------------------------------------------------------
  // Messages and the "busy" spinner
  // ---------------------------------------------------------------------------
  function showError(message) {
    els.alertText.textContent = message;
    els.alert.classList.remove("d-none");
    if (SMALL_SCREEN.matches && window.bootstrap) {
      window.bootstrap.Offcanvas.getOrCreateInstance(els.sidebar).show();
    }
  }

  function hideError() {
    els.alert.classList.add("d-none");
  }

  let busyCount = 0;
  function setBusy(on) {
    busyCount = Math.max(0, busyCount + (on ? 1 : -1));
    els.busy.classList.toggle("d-none", busyCount === 0);
  }

  // ---------------------------------------------------------------------------
  // REST API calls
  // ---------------------------------------------------------------------------
  class ApiError extends Error {}

  function errorMessage(data, status) {
    if (data && typeof data.detail === "string") return data.detail;
    if (data && typeof data === "object") {
      // Field errors look like {"location": ["..."], "name": ["..."]}
      const messages = Object.values(data).flat().filter((m) => typeof m === "string");
      if (messages.length) return messages.join(" ");
    }
    return `Something went wrong (error ${status}). Please try again.`;
  }

  async function api(url, { method = "GET", body } = {}) {
    const headers = { Accept: "application/json" };
    if (method !== "GET") headers["X-CSRFToken"] = config.csrfToken;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        credentials: "same-origin",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new ApiError("Can't reach the server. Check your connection and try again.");
    }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (response.status === 403) {
      throw new ApiError("Your session has ended. Reload the page and log in again.");
    }
    if (!response.ok) throw new ApiError(errorMessage(data, response.status));
    return data;
  }

  // ---------------------------------------------------------------------------
  // Groups
  // ---------------------------------------------------------------------------
  async function loadGroups(selectId) {
    state.groups = await api(config.urls.groups);
    els.groupSelect.replaceChildren(
      ...state.groups.map((group) => new Option(`${group.name} (${group.friend_count})`, group.id)),
    );
    els.groupPicker.classList.toggle("d-none", state.groups.length === 0);

    const saved = Number(localStorage.getItem(STORAGE_KEY));
    const wanted = [selectId, saved].find((id) => state.groups.some((group) => group.id === id));
    const id = wanted !== undefined ? wanted : state.groups.length ? state.groups[0].id : null;
    if (id === null) {
      showNoGroup();
      return;
    }
    els.groupSelect.value = String(id);
    await selectGroup(id);
  }

  function showNoGroup() {
    state.group = null;
    state.area = null;
    state.venues = null;
    Object.values(layers).forEach((layer) => layer.clearLayers());
    friendMarkers.clear();
    els.groupPanel.classList.add("d-none");
  }

  async function selectGroup(id) {
    hideError();
    stopPicking();
    localStorage.setItem(STORAGE_KEY, String(id));
    state.group = await api(groupUrl(id));
    state.area = null;
    state.venues = null;
    els.groupPanel.classList.remove("d-none");
    els.radius.value = state.group.search_radius_m;
    showRadius();
    renderAll();
    await recalculate({ fit: true });
  }

  function updateGroupOption() {
    const option = [...els.groupSelect.options].find((o) => Number(o.value) === state.group.id);
    if (option) option.textContent = `${state.group.name} (${state.group.friends.length})`;
  }

  /**
   * Ask PostGIS for the meeting point, lines, area, fairness and places
   * (POST /api/groups/{id}/compute/), then redraw everything.
   */
  async function recalculate({ fit = false } = {}) {
    const group = state.group;
    if (!group) return;
    const run = ++state.run;

    if (group.friends.length < 2) {
      // Not enough friends: the API has already cleared the saved results.
      Object.assign(group, { meeting_point: null, hull: null, fairness_score: null, fairness_label: null });
      group.friends.forEach((friend) => Object.assign(friend, { line_to_meeting: null, distance_m: null }));
      state.area = null;
      state.venues = null;
      renderAll();
      if (fit) fitToGroup();
      return;
    }

    setBusy(true);
    try {
      const result = await api(`${groupUrl(group.id)}compute/?${searchQuery()}`, { method: "POST" });
      let venues = result.venues;
      if (state.sort === "fairest") {
        venues = await api(`${groupUrl(group.id)}fair-venues/?${searchQuery()}`);
      }
      if (run !== state.run) return;
      state.group = result.group;
      state.area = result.area;
      state.venues = venues;
      renderAll();
      if (fit) fitToGroup();
    } catch (error) {
      if (run !== state.run) return;
      showError(error.message);
      renderAll(); // e.g. puts a dragged marker back where the server has it
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Friends
  // ---------------------------------------------------------------------------
  /** The name typed in the form, or null (with a message) if it can't be used yet. */
  function friendNameOrWarn() {
    const name = els.friendName.value.trim();
    if (!name) {
      showError("Type your friend's name first.");
      els.friendName.focus();
      return null;
    }
    if (state.group.friends.length >= config.maxFriends) {
      showError(`A group can have at most ${config.maxFriends} friends.`);
      return null;
    }
    return name;
  }

  async function addFriend(name, lat, lng, placeName) {
    hideError();
    stopPicking();
    setBusy(true);
    try {
      const friend = await api(config.urls.friends, {
        method: "POST",
        body: { group: state.group.id, name, place_name: placeName.slice(0, 255), location: geoPoint(lat, lng) },
      });
      state.group.friends.push(friend);
      els.friendForm.reset();
      els.addressResults.replaceChildren();
      await recalculate({ fit: true });
      if (!SMALL_SCREEN.matches) els.friendName.focus();
    } catch (error) {
      showError(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function moveFriend(friend, position) {
    hideError();
    try {
      const updated = await api(friendUrl(friend.id), {
        method: "PATCH",
        body: { location: geoPoint(position.lat, position.lng), place_name: "Moved on the map" },
      });
      state.group.friends = state.group.friends.map((f) => (f.id === updated.id ? updated : f));
    } catch (error) {
      showError(error.message); // e.g. dragged outside Dublin; the marker is put back below
    }
    await recalculate();
  }

  async function removeFriend(friend) {
    if (!window.confirm(`Remove ${friend.name} from the group?`)) return;
    hideError();
    try {
      await api(friendUrl(friend.id), { method: "DELETE" });
      state.group.friends = state.group.friends.filter((f) => f.id !== friend.id);
      map.closePopup();
      await recalculate();
    } catch (error) {
      showError(error.message);
    }
  }

  // ---------------------------------------------------------------------------
  // Drawing
  // ---------------------------------------------------------------------------
  function renderAll() {
    if (!state.group) return;
    renderFriends();
    renderMeeting();
    renderStats();
    renderPlaces();
    updateGroupOption();
  }

  function renderFriends() {
    const friends = state.group.friends;
    els.friendCount.textContent = String(friends.length);
    els.friendsEmpty.classList.toggle("d-none", friends.length > 0);

    layers.friends.clearLayers();
    layers.lines.clearLayers();
    friendMarkers.clear();
    friends.forEach((friend, index) => {
      const colour = colourOf(index);
      const marker = friendMarker(friend, colour);
      marker.addTo(layers.friends);
      friendMarkers.set(friend.id, marker);

      if (friend.line_to_meeting) {
        const points = friend.line_to_meeting.coordinates.map(([lng, lat]) => [lat, lng]);
        L.polyline(points, { color: colour, weight: 3, opacity: 0.9, dashArray: "6 8" })
          .bindTooltip(`${friend.name}: ${formatDistance(friend.distance_m)}`, { sticky: true })
          .addTo(layers.lines);
      }
    });
    els.friendList.replaceChildren(...friends.map(friendListItem));
  }

  function friendMarker(friend, colour) {
    const badge = el("div", "friend-marker", initials(friend.name));
    badge.style.backgroundColor = colour;
    const marker = L.marker(latLng(friend.location), {
      icon: L.divIcon({
        html: badge, className: "friend-icon", iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -16],
      }),
      draggable: true,
      autoPan: true,
      keyboard: true,
      title: `${friend.name} (drag to move)`,
      zIndexOffset: 1000,
    });
    marker.bindPopup(() => friendPopup(friend));
    marker.on("dragstart", () => marker.closePopup());
    marker.on("dragend", () => moveFriend(friend, marker.getLatLng()));
    return marker;
  }

  function friendPopup(friend) {
    const box = el("div", "map-popup");
    box.append(el("strong", "", friend.name));
    if (friend.place_name) box.append(el("div", "text-body-secondary", friend.place_name));
    if (friend.distance_m !== null && friend.distance_m !== undefined) {
      box.append(el("div", "", `${formatDistance(friend.distance_m)} to the meeting point`));
    }
    box.append(el("div", "text-body-secondary small", "Drag the marker to move them."));
    const remove = el("button", "btn btn-sm btn-outline-danger mt-1");
    remove.type = "button";
    remove.append(icon("bi-person-dash me-1"), document.createTextNode("Remove"));
    remove.addEventListener("click", () => removeFriend(friend));
    box.append(remove);
    return box;
  }

  function friendListItem(friend, index) {
    const item = el("li", "friend-item d-flex align-items-center gap-2 py-1");

    const dot = el("span", "friend-dot");
    dot.style.backgroundColor = colourOf(index);
    dot.setAttribute("aria-hidden", "true");

    const show = el("button", "btn btn-link btn-sm p-0 text-start text-decoration-none text-body flex-grow-1");
    show.type = "button";
    show.title = `Show ${friend.name} on the map`;
    const details = [friend.place_name, formatDistance(friend.distance_m)].filter(Boolean).join(" · ");
    show.append(el("span", "fw-semibold d-block", friend.name), el("span", "d-block text-body-secondary", details));
    show.addEventListener("click", () => {
      const marker = friendMarkers.get(friend.id);
      if (marker) flyToMarker(marker, 15);
    });

    const remove = el("button", "btn btn-sm btn-outline-danger border-0");
    remove.type = "button";
    remove.title = `Remove ${friend.name}`;
    remove.setAttribute("aria-label", `Remove ${friend.name}`);
    remove.append(icon("bi-x-lg"));
    remove.addEventListener("click", () => removeFriend(friend));

    item.append(dot, show, remove);
    return item;
  }

  function renderMeeting() {
    layers.meeting.clearLayers();
    layers.hull.clearLayers();
    layers.searchArea.clearLayers();
    const group = state.group;

    if (group.hull) {
      L.geoJSON(group.hull, {
        pane: "areas",
        interactive: false,
        style: { color: "#0d6efd", weight: 2, fillColor: "#0d6efd", fillOpacity: 0.08 },
      }).addTo(layers.hull);
    }
    if (state.venues && state.venues.search_area) {
      L.geoJSON(state.venues.search_area, {
        pane: "areas",
        interactive: false,
        style: { color: "#198754", weight: 2, dashArray: "4 6", fillColor: "#198754", fillOpacity: 0.06 },
      }).addTo(layers.searchArea);
    }
    if (group.meeting_point) {
      const star = el("div", "meeting-marker");
      star.append(icon("bi-star-fill"));
      L.marker(latLng(group.meeting_point), {
        icon: L.divIcon({ html: star, className: "meeting-icon", iconSize: [36, 36], iconAnchor: [18, 18], popupAnchor: [0, -18] }),
        keyboard: true,
        title: "Meeting point",
        zIndexOffset: 2000,
      })
        .bindPopup(meetingPopup)
        .addTo(layers.meeting);
    }
  }

  function meetingPopup() {
    const group = state.group;
    const [lat, lng] = latLng(group.meeting_point);
    const box = el("div", "map-popup");
    box.append(el("strong", "", "Meeting point"));
    if (group.fairness_score !== null) {
      box.append(el("div", "", `Fairness ${Math.round(group.fairness_score)} / 100 (${group.fairness_label})`));
    }
    box.append(el("div", "text-body-secondary small", `${lat.toFixed(5)}, ${lng.toFixed(5)}`));
    const link = el("a", "", "Open in OpenStreetMap");
    link.href = `https://www.openstreetmap.org/?mlat=${lat.toFixed(5)}&mlon=${lng.toFixed(5)}#map=17/${lat.toFixed(5)}/${lng.toFixed(5)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    box.append(link);
    return box;
  }

  function renderStats() {
    const group = state.group;
    const meter = els.fairnessMeter;
    const score = group.fairness_score;

    if (score === null || score === undefined) {
      const missing = 2 - group.friends.length;
      els.fairnessText.textContent = missing > 0 ? "Add two friends" : "Not worked out yet";
      els.fairnessBar.style.width = "0%";
      els.fairnessBar.className = "progress-bar";
      meter.setAttribute("aria-valuenow", "0");
      meter.setAttribute("aria-valuetext", "No score yet");
      els.resultStats.textContent = missing > 0
        ? `Add ${missing} more friend${missing === 1 ? "" : "s"} to find a meeting point.`
        : "";
      return;
    }

    const rounded = Math.round(score);
    const label = group.fairness_label;
    els.fairnessText.textContent = `${rounded} / 100 · ${label}`;
    els.fairnessBar.style.width = `${Math.max(score, 3)}%`;
    els.fairnessBar.className = `progress-bar ${FAIRNESS_COLOURS[label] || ""}`;
    meter.setAttribute("aria-valuenow", String(rounded));
    meter.setAttribute("aria-valuetext", `${rounded} out of 100, ${label}`);

    const parts = [];
    const distances = group.friends.map((f) => f.distance_m).filter((d) => d !== null && d !== undefined);
    if (distances.length) {
      const mean = distances.reduce((sum, d) => sum + d, 0) / distances.length;
      parts.push(`Average trip ${formatDistance(mean)}`, `longest ${formatDistance(Math.max(...distances))}`);
    }
    if (state.area && state.area.area_m2) {
      const category = els.category.value;
      const inside = state.area.venues_inside[category] || 0;
      parts.push(`group area ${formatArea(state.area.area_m2)} with ${inside} ${plural(category, inside)} inside`);
    }
    els.resultStats.textContent = parts.length ? `${parts.join(" · ")}.` : "";
  }

  function renderPlaces() {
    layers.places.clearLayers();
    els.venueList.replaceChildren();
    els.fallbackNote.classList.add("d-none");

    const search = state.venues;
    const features = search ? search.venues.features : [];
    els.venueEmpty.classList.toggle("d-none", Boolean(search));
    if (!search) return;

    const category = search.categories[0];
    if (search.fallback) {
      els.fallbackNote.textContent = features.length
        ? `No ${plural(category, 2)} within ${search.radius_m} m of the meeting point. Showing the ${features.length} nearest.`
        : `No ${plural(category, 2)} found.`;
      els.fallbackNote.classList.remove("d-none");
    } else if (!features.length) {
      els.fallbackNote.textContent = `No ${plural(category, 2)} found.`;
      els.fallbackNote.classList.remove("d-none");
    }

    features.forEach((feature, index) => {
      const marker = placeMarker(feature, index + 1);
      marker.addTo(layers.places);
      els.venueList.append(placeListItem(feature, marker));
    });
  }

  function placeMarker(feature, number) {
    const props = feature.properties;
    const badge = el("div", `place-marker place-${props.category}`, String(number));
    const marker = L.marker(latLng(feature.geometry), {
      icon: L.divIcon({ html: badge, className: "place-icon", iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -13] }),
      keyboard: true,
      title: props.name,
      zIndexOffset: 500,
    });
    marker.bindPopup(() => placePopup(props));
    return marker;
  }

  function placePopup(props) {
    const build = window.MeetHalfway.venuePopup;
    const box = build ? build(props) : el("div", "venue-popup", props.name);
    box.append(el("div", "fw-semibold mt-1", `${formatDistance(props.distance_m)} from the meeting point`));
    if (props.fairness_score !== undefined) {
      box.append(el("div", "", `Fairness ${Math.round(props.fairness_score)} / 100 (${props.fairness_label})`));
      box.append(el("div", "text-body-secondary", `Longest trip ${formatDistance(props.longest_trip_m)}`));
    }
    return box;
  }

  function placeListItem(feature, marker) {
    const props = feature.properties;
    const item = el("li", "list-group-item d-flex align-items-start gap-1 px-2 py-1");
    const button = el("button", "btn btn-link p-0 text-start text-decoration-none text-body flex-grow-1 small");
    button.type = "button";
    const facts = [formatDistance(props.distance_m)];
    if (props.fairness_score !== undefined) facts.push(`fairness ${Math.round(props.fairness_score)}`);
    if (props.cuisine) facts.push(props.cuisine);
    button.append(el("span", "fw-semibold d-block", props.name), el("span", "text-body-secondary", facts.join(" · ")));
    button.addEventListener("click", () => flyToMarker(marker, 17));
    item.append(button);
    return item;
  }

  function fitToGroup() {
    const points = state.group.friends.map((friend) => latLng(friend.location));
    if (state.group.meeting_point) points.push(latLng(state.group.meeting_point));
    if (points.length === 1) map.setView(points[0], 15);
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 16 });
  }

  // ---------------------------------------------------------------------------
  // Picking a location on the map
  // ---------------------------------------------------------------------------
  function startPicking() {
    const name = friendNameOrWarn();
    if (!name) return;
    state.picking = true;
    els.pickOnMap.setAttribute("aria-pressed", "true");
    els.pickOnMap.classList.add("active");
    map.getContainer().classList.add("is-picking");
    els.mapHint.textContent = `Click the map where ${name} is. Press Esc to cancel.`;
    els.mapHint.classList.remove("d-none");
    closeSidebarOnSmallScreens();
  }

  function stopPicking() {
    state.picking = false;
    els.pickOnMap.setAttribute("aria-pressed", "false");
    els.pickOnMap.classList.remove("active");
    map.getContainer().classList.remove("is-picking");
    els.mapHint.classList.add("d-none");
  }

  map.on("click", (event) => {
    if (!state.picking) return;
    const name = els.friendName.value.trim();
    if (!name) {
      stopPicking();
      return;
    }
    addFriend(name, event.latlng.lat, event.latlng.lng, "Picked on the map");
  });

  // ---------------------------------------------------------------------------
  // Address search (only when the user presses Enter or the Search button)
  // ---------------------------------------------------------------------------
  function shortPlaceName(displayName) {
    return displayName.split(",").slice(0, 2).join(",").trim();
  }

  function showAddressResults(results, query) {
    if (!results.length) {
      els.addressResults.replaceChildren(
        el("div", "list-group-item px-1 text-body-secondary", `Nothing found in Dublin for "${query}".`),
      );
      return;
    }
    els.addressResults.replaceChildren(
      ...results.map((place) => {
        const button = el("button", "list-group-item list-group-item-action px-1 py-1");
        button.type = "button";
        button.append(icon("bi-geo-alt me-1"), document.createTextNode(place.name));
        button.addEventListener("click", () => {
          const name = friendNameOrWarn();
          if (name) addFriend(name, place.lat, place.lon, shortPlaceName(place.name));
        });
        return button;
      }),
    );
    els.addressResults.firstElementChild.focus(); // keyboard users land on the first result
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------
  els.alertClose.addEventListener("click", hideError);

  els.groupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = els.groupName.value.trim();
    if (!name) return;
    hideError();
    try {
      const group = await api(config.urls.groups, { method: "POST", body: { name } });
      els.groupForm.reset();
      await loadGroups(group.id);
      els.friendName.focus();
    } catch (error) {
      showError(error.message);
    }
  });

  els.groupSelect.addEventListener("change", () => {
    selectGroup(Number(els.groupSelect.value)).catch((error) => showError(error.message));
  });

  els.groupDelete.addEventListener("click", async () => {
    if (!state.group) return;
    if (!window.confirm(`Delete the group "${state.group.name}" and all its friends?`)) return;
    try {
      await api(groupUrl(state.group.id), { method: "DELETE" });
      localStorage.removeItem(STORAGE_KEY);
      await loadGroups();
    } catch (error) {
      showError(error.message);
    }
  });

  els.friendForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = friendNameOrWarn();
    if (!name) return;
    const query = els.friendAddress.value.trim();
    if (query.length < 3) {
      showError("Type at least 3 letters of an address or place, then press Enter.");
      els.friendAddress.focus();
      return;
    }
    hideError();
    els.addressSearch.disabled = true;
    els.addressResults.replaceChildren(el("div", "list-group-item px-1 text-body-secondary", "Searching…"));
    try {
      const data = await api(`${config.urls.geocode}?${new URLSearchParams({ q: query })}`);
      showAddressResults(data.results, query);
    } catch (error) {
      els.addressResults.replaceChildren();
      showError(error.message);
    } finally {
      els.addressSearch.disabled = false;
    }
  });

  els.pickOnMap.addEventListener("click", () => (state.picking ? stopPicking() : startPicking()));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.picking) stopPicking();
  });

  els.useLocation.addEventListener("click", () => {
    const name = friendNameOrWarn();
    if (!name) return;
    if (!("geolocation" in navigator) || !window.isSecureContext) {
      showError("Browsers only share your location on HTTPS or localhost. Search for an address or pick on the map instead.");
      return;
    }
    els.useLocation.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        els.useLocation.disabled = false;
        addFriend(name, position.coords.latitude, position.coords.longitude, "Current location");
      },
      (error) => {
        els.useLocation.disabled = false;
        showError(error.code === error.PERMISSION_DENIED
          ? "Location access is blocked. Allow it in the browser, or search for an address instead."
          : "Couldn't get your location. Search for an address instead.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });

  // Radius slider: update the label while sliding, save and search when released.
  function showRadius() {
    els.radiusValue.textContent = `${els.radius.value} m`;
  }

  let radiusTimer = null;
  els.radius.addEventListener("input", showRadius);
  els.radius.addEventListener("change", () => {
    clearTimeout(radiusTimer);
    radiusTimer = setTimeout(async () => {
      if (!state.group) return;
      const radius = Number(els.radius.value);
      try {
        await api(groupUrl(state.group.id), { method: "PATCH", body: { search_radius_m: radius } });
        state.group.search_radius_m = radius;
      } catch (error) {
        showError(error.message);
      }
      await recalculate();
    }, 300);
  });

  els.category.addEventListener("change", () => recalculate());

  document.querySelectorAll('input[name="sort"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.sort = input.value;
      recalculate();
    });
  });

  // ---------------------------------------------------------------------------
  // Start
  // ---------------------------------------------------------------------------
  els.radius.min = config.radius.min; // min and max first, or the value would be clamped
  els.radius.max = config.radius.max;
  els.radius.value = config.radius.default;
  showRadius();

  loadGroups().catch((error) => showError(error.message));
})();
