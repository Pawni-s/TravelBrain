(function () {
  const $ = id => document.getElementById(id);
  const form = $('routeForm'), error = $('error'), results = $('results'), button = $('planButton');
  const currencyKey = 'travelbrain.currency', tripKey = 'travelbrain.currentTrip';
  let trip = null; try { trip = JSON.parse(localStorage.getItem(tripKey) || 'null'); } catch (_) {}
  try { document.documentElement.dataset.theme = localStorage.getItem('travelbrain.theme') || 'dark'; } catch (_) {}
  const savedCurrency = (() => { try { return localStorage.getItem(currencyKey) || (trip && trip.currency) || 'INR'; } catch (_) { return 'INR'; } })();
  $('routeCurrency').value = savedCurrency;
  $('routeCurrency').addEventListener('change', () => { try { localStorage.setItem(currencyKey, $('routeCurrency').value); } catch (_) {} });
  if (trip && (trip.query || trip.answer)) {
    $('tripContextTitle').textContent = 'Linked to your current TravelBrain trip';
    $('tripContextText').textContent = 'Your request: ' + (trip.query || 'Trip conversation') + '\n\nLatest plan summary: ' + String(trip.answer || '').slice(0, 850) + (trip.currency && trip.currency !== savedCurrency ? `\n\nCurrency note: the earlier AI answer was generated in ${trip.currency}; new planning estimates use ${savedCurrency}. No automatic conversion is applied.` : '');
    const source = (trip.query || '') + '\n' + (trip.answer || '');
    const match = source.match(/(?:trip|travel|vacation|holiday)\s+(?:to|in)\s+([A-Z][A-Za-z .'-]{2,35})(?=\s+(?:from|for|with|in|on|during|focused|and|,|\.|$))/) || source.match(/(?:to|in|around|visit(?:ing)?)\s+([A-Z][A-Za-z .'-]{2,35})(?=\s+(?:from|for|with|in|on|during|focused|and|,|\.|$))/);
    if (match) $('destination').value = match[1].trim();
    $('profile').value = /luxury|resort|relax/i.test(source) ? 'luxury' : /adventure|hiking|trek/i.test(source) ? 'adventure' : /food|restaurant|cuisine/i.test(source) ? 'food' : /culture|museum|temple|sightseeing/i.test(source) ? 'culture' : 'balanced';
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.hidden = true; results.hidden = true; button.disabled = true; button.textContent = 'Researching places and building options…';
    const attractions = $('attractions').value.split(/\n/).map(s => s.trim()).filter(Boolean);
    const tripContext = trip ? [...(trip.history || []).flatMap(item => [item.query, item.answer]), trip.query, trip.answer, trip.itinerary, trip.hotelResults].filter(Boolean).join('\n\n').slice(0, 5000) : '';
    try {
      const response = await fetch('/api/itinerary/plan-options', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ destination:$('destination').value.trim(), hotel_name:$('hotelName').value.trim(), attractions, start_time:$('startTime').value, end_time:$('endTime').value, profile:$('profile').value, buffer_minutes:Number($('buffer').value), currency:$('routeCurrency').value, trip_context:tripContext }) });
      const data = await response.json(); if (!response.ok) {
        let message = data.error || 'Could not build itinerary options.';
        if (data.missing_details && data.missing_details.length) message += '\nMissing details: ' + data.missing_details.join(', ');
        if (data.food_places && data.food_places.length) renderFood(data.food_places);
        if (data.research_notes) renderNotes(data.research_notes);
        if ((data.food_places && data.food_places.length) || (data.research_notes && data.research_notes.length)) results.hidden = false;
        throw new Error(message);
      }
      $('resultTitle').textContent = 'Day-plan options for ' + data.destination;
      $('resultSummary').textContent = `${data.selected_count} selected places · ${data.options.length} pacing options · hotel start and return`;
      const container = $('options'); container.replaceChildren();
      data.options.forEach(option => {
        const card = document.createElement('article'); card.className = 'tool-option';
        const title = document.createElement('h3'); title.textContent = option.name; card.appendChild(title);
        const summary = document.createElement('p'); summary.className = option.feasible ? 'tool-muted' : 'tool-alert';
        summary.textContent = option.feasible ? `Estimated total time: ${duration(option.total_duration_minutes)} · ${option.buffer_minutes} min between stops · ${option.meal_break_minutes} min meal break · All selected places scheduled` : 'This pace does not fit the current opening-hour and day-length constraints.'; card.appendChild(summary);
        (option.route.days || []).forEach(day => {
          const dayTitle = document.createElement('h4'); dayTitle.style.marginTop = '14px'; dayTitle.textContent = `Day ${day.day}: ${day.area}`; card.appendChild(dayTitle);
          if (!day.feasible) { (day.reasons || []).forEach(reason => { const p = document.createElement('p'); p.className = 'tool-alert'; p.textContent = reason; card.appendChild(p); }); (day.suggestions || []).forEach(suggestion => { const p = document.createElement('p'); p.className = 'tool-muted'; p.textContent = 'Try: ' + suggestion; card.appendChild(p); }); return; }
          const metrics = document.createElement('p'); metrics.className = 'tool-muted'; metrics.textContent = `Route distance: ${(day.total_distance_km || 0).toFixed(1)} km estimated · Travel: ${duration(day.total_travel_minutes)} · Visits: ${duration(day.total_visit_minutes)} · Buffers: ${duration(day.total_buffer_minutes || 0)} · Return to hotel: ${day.hotel_return_time}`; card.appendChild(metrics);
          (day.route || []).forEach(stop => {
            const item = document.createElement('div'); item.className = 'tool-stop';
            const name = document.createElement('strong'); name.textContent = `${stop.order}. ${stop.name}`; item.appendChild(name);
            const detail = document.createElement('p'); detail.className = 'tool-muted'; detail.textContent = `Arrive ${stop.arrival_time} · Visit ${stop.visit_start}–${stop.visit_end} (${stop.visit_minutes} min) · ${Number(stop.distance_from_previous_km || 0).toFixed(1)} km from previous stop · approx. ${stop.travel_from_previous_minutes} min travel · ${stop.buffer_after_minutes || 0} min buffer after${stop.meal_break_after_minutes ? ` · ${stop.meal_break_after_minutes} min meal break after this stop` : ""}`; item.appendChild(detail);
            const hours = document.createElement('p'); hours.className = 'tool-muted'; hours.textContent = `Listed opening hours: ${stop.opening_hours} · Hours data: ${stop.hours_confidence || "unknown"} · Location data: ${stop.coordinate_confidence || "unknown"}`; item.appendChild(hours); card.appendChild(item);
          });
          const ret = document.createElement('p'); ret.className = 'tool-muted'; ret.textContent = `Hotel return leg: ${(day.hotel_return_distance_km || 0).toFixed(1)} km · approx. ${day.hotel_return_travel_minutes || 0} min`; card.appendChild(ret);
        });
        container.appendChild(card);
      });
      renderFood(data.food_places || []); renderNotes(data.notes || []); $('travelNotice').textContent = data.travel_time_notice || ''; results.hidden = false;
    } catch (err) { error.textContent = err.message || 'Unexpected error.'; error.hidden = false; }
    finally { button.disabled = false; button.textContent = 'Build my day-plan options'; }
  });
  function duration(minutes) { minutes = Number(minutes || 0); const h = Math.floor(minutes / 60), m = minutes % 60; return h ? `${h} hr ${m} min` : `${m} min`; }
  function renderFood(items) { const box = $('foodPlaces'); box.replaceChildren(); if (!items.length) { const p = document.createElement('p'); p.className = 'tool-muted'; p.textContent = 'No nearby food suggestions were returned. Try again with a more specific destination or check the main trip chat.'; box.appendChild(p); return; } items.forEach(place => { const row = document.createElement('div'); row.className = 'tool-row'; const left = document.createElement('div'); const name = document.createElement('strong'); name.textContent = place.name || 'Local food option'; const detail = document.createElement('p'); detail.className = 'tool-muted'; detail.textContent = [place.area, place.specialty, place.meal, place.price_level].filter(Boolean).join(' · '); left.append(name, detail); row.appendChild(left); box.appendChild(row); }); }
  function renderNotes(items) { const box = $('notes'); box.replaceChildren(); (items || []).forEach(note => { const p = document.createElement('p'); p.className = 'tool-muted'; p.style.margin = '8px 0'; p.textContent = typeof note === 'string' ? note : Object.entries(note || {}).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · '); box.appendChild(p); }); }
})();
