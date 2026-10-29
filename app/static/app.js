/* All hostile strings reach the DOM through textContent. No HTML interpolation. */
'use strict';
const $ = id => document.getElementById(id);
const number = value => new Intl.NumberFormat('en-US').format(value || 0);
const state = {range: '24h', markers: new Map(), feedIds: new Set(), chart: null, refreshing: false, queued: false};
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}
async function api(path) {
  const response = await fetch(path, {credentials: 'omit', signal: AbortSignal.timeout(8000)});
  if (!response.ok) throw new Error('Data is temporarily unavailable. Retrying automatically.');
  return response.json();
}
let map;
try {
  map = L.map('map', {zoomControl: false, minZoom: 1, maxZoom: 10, worldCopyJump: true}).setView([23, 8], 2);
  L.control.zoom({position: 'bottomright'}).addTo(map);
  // Self-hosted public-domain land geometry remains visible when tile egress is unavailable.
  map.createPane('world-outline');
  map.getPane('world-outline').style.zIndex = '150';
  fetch('/static/world-land.geojson', {credentials: 'omit'})
    .then(response => {if (!response.ok) throw new Error('World outline unavailable'); return response.json();})
    .then(data => L.geoJSON(data, {pane: 'world-outline', interactive: false, style: {color: '#2b4149', weight: .6, fillColor: '#16262d', fillOpacity: 1}}).addTo(map))
    .catch(() => {});

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" rel="noopener noreferrer">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions" rel="noopener noreferrer">CARTO</a>',
    subdomains: 'abcd', maxZoom: 19, noWrap: true
  }).addTo(map);
} catch (_) {
  $('map').textContent = 'Map assets could not be loaded.';
}
function renderMap(rows) {
  if (!map) return;
  const seen = new Set();
  for (const row of rows) {
    if (!Number.isFinite(row.lat) || !Number.isFinite(row.lon)) continue;
    const key = row.ip + ':' + row.lat + ':' + row.lon;
    seen.add(key);
    let marker = state.markers.get(key);
    if (!marker) {
      marker = L.circleMarker([row.lat, row.lon], {weight: 1, fillOpacity: .55}).addTo(map);
      state.markers.set(key, marker);
    }
    marker.setStyle({radius: Math.min(15, 4 + Math.log2(row.attempts + 1)), color: row.banned ? '#e5aa68' : '#45c8b0'});
    const popup = node('div');
    for (const [label, value] of [['Source', row.ip], ['Location', [row.city, row.country].filter(Boolean).join(', ') || 'Unknown'], ['Network', [row.asn && 'AS' + row.asn, row.asn_org].filter(Boolean).join(' · ')], ['PTR', row.rdns], ['Attempts', number(row.attempts)], ['First seen', row.first_seen], ['Last seen', row.last_seen], ['Admin SSH ban', row.banned ? 'Observed ban' : 'No retained ban'], ['Tor exit', row.is_tor ? 'Listed' : 'Not listed / unknown']]) {
      if (value !== null && value !== undefined && value !== '') popup.append(node('div', 'popup-row', label + ': ' + value));
    }
    marker.bindPopup(popup);
  }
  for (const [key, marker] of state.markers) {
    if (!seen.has(key)) {marker.remove(); state.markers.delete(key);}
  }
}
function renderRanking(id, rows) {
  const target = $(id);
  const fragment = document.createDocumentFragment();
  if (!rows.length) fragment.append(node('li', 'empty', 'No qualifying observations yet.'));
  rows.slice(0, id === 'top-details' ? 20 : 7).forEach((row, i) => {
    const li = node('li');
    const value = node('span', 'rank-value', row.value ?? (row.username + ' : ' + row.password));
    value.append(node('span', 'rank-sources', number(row.distinct_ips) + ' distinct sources'));
    li.append(node('span', 'rank-num', String(i + 1).padStart(2, '0')), value, node('span', 'rank-count', number(row.count)));
    fragment.append(li);
  });
  target.replaceChildren(fragment);
}
function addFeed(row, live = false) {
  if (state.feedIds.has(row.id)) return;
  state.feedIds.add(row.id);
  const feed = $('feed');
  feed.querySelector('.empty')?.remove();
  const item = node('li', live ? 'new' : '');
  const detail = node('span', 'feed-ip', row.ip || 'Unknown source');
  detail.append(node('span', 'feed-info', [row.type.replaceAll('_', ' '), row.country_code, row.username].filter(Boolean).join(' · ')));
  const time = node('time', '', new Date(row.ts).toLocaleTimeString('en-GB', {timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit'}));
  time.dateTime = row.ts;
  item.append(node('span', 'signal' + (row.type === 'f2b_ban' ? ' ban' : '')), detail, time);
  feed.prepend(item);
  if (live) {
    if (map && Number.isFinite(row.lat) && Number.isFinite(row.lon)) {
      const key = row.ip + ':' + row.lat + ':' + row.lon;
      if (!state.markers.has(key) && state.markers.size < 1000) {
        const marker = L.circleMarker([row.lat, row.lon], {radius: 5, weight: 1, color: '#45c8b0', fillOpacity: .55}).addTo(map);
        marker.bindPopup(node('div', 'popup-row', row.ip + ' · ' + (row.country || 'Unknown')));
        state.markers.set(key, marker);
      }
    }
    for (const marker of state.markers.values()) {
      const position = marker.getLatLng();
      if (position.lat === row.lat && position.lng === row.lon) {
        const element = marker.getElement();
        element?.classList.add('pulse');
        setTimeout(() => element?.classList.remove('pulse'), 1600);
      }
    }
  }
  while (feed.children.length > 50) feed.lastChild.remove();
  // Cursor deduplication stays bounded even on long-lived tabs.
  if (state.feedIds.size > 500) state.feedIds = new Set([...state.feedIds].slice(-100));
  $('feed-count').textContent = number(feed.children.length) + ' EVENTS';
}
function renderStats(stats) {
  $('attempts').textContent = number(stats.attempts);
  $('attempts').nextElementSibling.textContent = number(stats.attempts_today) + ' today · ' + number(stats.lifetime_attempts) + ' lifetime';
  $('sources').textContent = number(stats.unique_ips);
  $('passwords').textContent = number(stats.passwords);
  $('repeat').textContent = Math.round(stats.repeat_ratio * 100) + '%';
  $('uptime').textContent = 'ONLINE ' + Math.floor(stats.uptime_seconds / 3600) + 'H ' + Math.floor(stats.uptime_seconds % 3600 / 60) + 'M';
  const series = new Map(stats.series.map(row => [row.hour, row.count]));
  const hours = Array.from({length: 24}, (_, i) => {
    const date = new Date(); date.setUTCMinutes(0, 0, 0); date.setUTCHours(date.getUTCHours() - 23 + i);
    return date.toISOString().replace('.000Z', 'Z');
  });
  const values = hours.map(hour => series.get(hour) || 0);
  const labels = hours.map(hour => hour.slice(11, 13) + ':00');
  if (window.Chart) {
    if (!state.chart) {
      state.chart = new Chart($('timeline'), {type: 'bar', data: {labels, datasets: [{data: values, backgroundColor: '#83c681', hoverBackgroundColor: '#a5ed8a', borderRadius: 2, maxBarThickness: 12}]}, options: {responsive: true, maintainAspectRatio: false, animation: false, plugins: {legend: {display: false}}, scales: {x: {grid: {display: false}, ticks: {color: '#718697', font: {size: 8}, maxTicksLimit: 8}, border: {display: false}}, y: {beginAtZero: true, grid: {color: '#23303c66'}, ticks: {precision: 0, color: '#718697', font: {size: 8}, maxTicksLimit: 4}, border: {display: false}}}}});
    } else {state.chart.data.labels = labels; state.chart.data.datasets[0].data = values; state.chart.update();}
  }
  const valuesByCell = new Map(stats.heatmap.map(row => [row.day + ':' + row.hour, row.count]));
  const maximum = Math.max(1, ...stats.heatmap.map(row => row.count));
  const fragment = document.createDocumentFragment();
  fragment.append(node('span'));
  for (let hour = 0; hour < 24; hour++) fragment.append(node('span', 'heat-label', hour % 6 === 0 ? String(hour).padStart(2, '0') : ''));
  ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].forEach((label, day) => {
    fragment.append(node('span', 'heat-label', label));
    for (let hour = 0; hour < 24; hour++) {
      const count = valuesByCell.get(((day + 1) % 7) + ':' + hour) || 0;
      const cell = node('span', 'heat-cell');
      cell.dataset.level = String(count ? Math.max(1, Math.ceil(count / maximum * 4)) : 0);
      cell.title = label + ' ' + hour + ':00 UTC · ' + number(count) + ' attempts';
      fragment.append(cell);
    }
  });
  $('heatmap').replaceChildren(fragment);
}
async function refresh() {
  if (state.refreshing) {state.queued = true; return;}
  state.refreshing = true;
  const selected = state.range;
  const kind = $('detail-kind').value;
  try {
    const range = '?range=' + encodeURIComponent(selected);
    const [stats, locations, passwords, usernames, countries, details] = await Promise.all([
      api('/api/stats' + range), api('/api/map' + range), api('/api/top/passwords' + range),
      api('/api/top/usernames' + range), api('/api/top/countries' + range), api('/api/top/' + kind + range)
    ]);
    if (selected === state.range && kind === $('detail-kind').value) {
      renderStats(stats); renderMap(locations);
      renderRanking('top-passwords', passwords); renderRanking('top-usernames', usernames);
      renderRanking('top-countries', countries); renderRanking('top-details', details);
    }
    $('error').hidden = true;
  } catch (error) {$('error').hidden = false; $('error').textContent = error.message;}
  finally {state.refreshing = false; if (state.queued) {state.queued = false; void refresh();}}
}
$('ranges').addEventListener('click', event => {
  const button = event.target.closest('button[data-range]');
  if (!button) return;
  state.range = button.dataset.range;
  document.querySelectorAll('#ranges button').forEach(item => {item.classList.toggle('selected', item === button); item.setAttribute('aria-pressed', String(item === button));});
  void refresh();
});
$('detail-kind').addEventListener('change', () => void refresh());
$('about-button').addEventListener('click', () => $('about').showModal());
$('close-about').addEventListener('click', () => $('about').close());
async function init() {
  try {
    const config = await api('/api/config');
    $('geo-notice').hidden = config.geo_city;
    $('privacy-caption').textContent = 'Only passwords observed from at least ' + config.password_min_ips + ' distinct sources.';
    $('about-threshold').textContent = config.password_min_ips;
    $('about-retention').textContent = config.retention_days;
    $('retention').textContent = config.retention_days + '-day raw retention. No cookies. No trackers.';
    // Open stream before fetching history; IDs prevent reconnect/history duplicates.
    const stream = new EventSource('/api/stream');
    stream.onopen = () => {$('connection').textContent = 'LIVE SENSOR'; $('connection').classList.add('live');};
    stream.onerror = () => {$('connection').textContent = 'RECONNECTING'; $('connection').classList.remove('live');};
    stream.addEventListener('attack', event => {
      try {addFeed(JSON.parse(event.data), true);} catch (_) { /* malformed transport data is ignored */ }
    });
    const events = await api('/api/events?limit=30');
    events.reverse().forEach(row => addFeed(row));
  } catch (error) {$('error').hidden = false; $('error').textContent = error.message;}
  await refresh();
}
void init();
// Refresh aggregates at the cache cadence, independent of attack volume.
setInterval(() => {if (!document.hidden) void refresh();}, 10000);
