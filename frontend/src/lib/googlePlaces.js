/**
 * FA-03 · Google Places JS API loader (frontend-only, singleton).
 *
 * - Reads API key from ``process.env.REACT_APP_GOOGLE_MAPS_API_KEY``.
 * - Loads the Maps JS API with the Places library exactly once.
 * - Handles the already-loaded case + concurrent callers via a shared
 *   in-flight promise.
 * - Fails safely: missing key or network failure resolves to ``null`` so
 *   callers can fall back to a plain text input.
 * - Never logs / exposes / stores the API key.
 * - No map, no geocoder, no distance matrix — Places-only.
 */

const SCRIPT_ID = "ace-google-maps-loader";
let _promise = null;

export function isPlacesAvailable() {
  return typeof window !== "undefined"
    && !!(window.google && window.google.maps && window.google.maps.places);
}

export function loadGooglePlaces() {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (isPlacesAvailable()) return Promise.resolve(window.google.maps.places);
  if (_promise) return _promise;

  const key = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  if (!key) {
    // No key configured — silently disable autocomplete. Callers fall back
    // to a plain text input.
    _promise = Promise.resolve(null);
    return _promise;
  }

  _promise = new Promise((resolve) => {
    // Reuse existing tag if another loader placed it.
    const existing = document.getElementById(SCRIPT_ID);
    if (existing) {
      existing.addEventListener("load", () => resolve(isPlacesAvailable() ? window.google.maps.places : null));
      existing.addEventListener("error", () => resolve(null));
      return;
    }
    const s = document.createElement("script");
    s.id = SCRIPT_ID;
    s.async = true;
    s.defer = true;
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places&loading=async&v=weekly`;
    s.onload = () => resolve(isPlacesAvailable() ? window.google.maps.places : null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
  return _promise;
}
