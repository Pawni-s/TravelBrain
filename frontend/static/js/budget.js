(function () {
  const $ = id => document.getElementById(id);
  const form = $('budgetForm'), error = $('error'), results = $('results');
  const fields = ['travel', 'accommodation', 'food', 'local_transport', 'activities', 'miscellaneous'];
  const currencyKey = 'travelbrain.currency', tripKey = 'travelbrain.currentTrip';
  let trip = null;
  try { trip = JSON.parse(localStorage.getItem(tripKey) || 'null'); } catch (_) {}
  try { document.documentElement.dataset.theme = localStorage.getItem('travelbrain.theme') || 'dark'; } catch (_) {}
  const savedCurrency = (() => { try { return localStorage.getItem(currencyKey) || (trip && trip.currency) || 'INR'; } catch (_) { return 'INR'; } })();
  $('budgetCurrency').value = savedCurrency;
  const currency = () => $('budgetCurrency').value;
  const money = value => new Intl.NumberFormat('en', { style: 'currency', currency: currency(), maximumFractionDigits: 0 }).format(Number(value || 0));
  $('budgetCurrency').addEventListener('change', () => { try { localStorage.setItem(currencyKey, currency()); } catch (_) {} });
  if (trip && (trip.query || trip.answer)) {
    const contextText = [trip.query, ...(trip.history || []).map(item => item.query || '')].join(' ');
    const daysMatch = contextText.match(/(\d{1,2})\s*[- ]?day/i);
    if (daysMatch && Number(daysMatch[1]) > 0) $('duration').value = Number(daysMatch[1]);
    if (/luxury|resort|relax/i.test(contextText)) $('profile').value = 'luxury';
    else if (/adventure|hiking|trek/i.test(contextText)) $('profile').value = 'adventure';
    else if (/food|restaurant|cuisine/i.test(contextText)) $('profile').value = 'food';
    else if (/culture|museum|temple|sightseeing/i.test(contextText)) $('profile').value = 'culture';
    $('tripContextTitle').textContent = 'Linked to your current TravelBrain trip';
    $('tripContextText').textContent = 'Your request: ' + (trip.query || 'Trip conversation') + '\n\nLatest plan summary: ' + String(trip.answer || '').slice(0, 900) + (trip.currency && trip.currency !== savedCurrency ? `\n\nCurrency note: the earlier AI answer was generated in ${trip.currency}. This page uses ${savedCurrency}; earlier amounts are not automatically converted. Ask TravelBrain to restate the plan in the selected currency before relying on old figures.` : '');
    if (trip.currency) $('budgetCurrency').value = currency();
  }
  $('estimateTrip').addEventListener('click', async () => {
    const status = $('estimateStatus'); status.textContent = ''; $('estimateAssumptions').replaceChildren();
    const tripContext = trip ? [...(trip.history || []).flatMap(item => [item.query, item.answer]), trip.query, trip.answer, trip.itinerary, trip.hotelResults].filter(Boolean).join('\n\n').slice(0, 7000) : '';
    if (!tripContext) { status.textContent = 'Start a trip in the TravelBrain chat first, then return here to estimate its costs.'; return; }
    const button = $('estimateTrip'); button.disabled = true; button.textContent = 'Estimating from your trip…';
    try {
      const response = await fetch('/api/budget/estimate-trip', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ trip_context:tripContext, currency:currency(), profile:$('profile').value, duration_days:Number($('duration').value), travellers:Number($('travellers').value) }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Could not estimate trip costs.');
      $('budget').value = Math.round(data.budget); fields.forEach(key => { $(key).value = Math.round(data.costs[key] || 0); });
      status.textContent = `Estimated for ${data.duration_days} days and ${data.travellers} traveller(s) in ${data.currency}. Review every amount before analyzing.`;
      (data.assumptions || []).forEach(note => { const p = document.createElement('p'); p.textContent = '• ' + note; p.style.margin = '5px 0'; $('estimateAssumptions').appendChild(p); });
      const disclaimer = document.createElement('p'); disclaimer.textContent = data.disclaimer; disclaimer.style.marginTop = '8px'; $('estimateAssumptions').appendChild(disclaimer);
    } catch (err) { status.textContent = err.message || 'Unexpected error.'; }
    finally { button.disabled = false; button.textContent = 'Estimate costs from my trip'; }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault(); error.hidden = true; results.hidden = true;
    const costs = {}; fields.forEach(key => costs[key] = Number($(key).value));
    const tripContext = trip ? [...(trip.history || []).flatMap(item => [item.query, item.answer]), trip.query, trip.answer, trip.itinerary, trip.hotelResults].filter(Boolean).join('\n\n').slice(0, 5000) : '';
    const payload = { budget: Number($('budget').value), profile: $('profile').value, costs, currency: currency(), trip_context: tripContext, duration_days: Number($('duration').value) };
    try {
      const response = await fetch('/api/budget/analyze', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || data.error || 'Could not analyze the budget.');
      $('outBudget').textContent = money(data.budget); $('outTotal').textContent = money(data.total);
      $('balanceLabel').textContent = data.over_budget ? 'Over budget' : 'Remaining';
      $('outBalance').textContent = money(Math.abs(data.remaining)); $('outBalance').className = data.over_budget ? 'tool-alert' : '';
      const breakdown = $('breakdown'); breakdown.replaceChildren();
      data.breakdown.forEach(item => { const row = document.createElement('div'); row.className = 'tool-row'; const label = document.createElement('span'); label.textContent = item.label; const amount = document.createElement('strong'); amount.textContent = money(item.amount); row.append(label, amount); breakdown.appendChild(row); });
      const allocation = $('allocation'); allocation.replaceChildren();
      data.allocation.forEach(item => { const row = document.createElement('div'); row.className = 'tool-row'; const label = document.createElement('span'); label.textContent = `${item.label} · ${Math.round(item.weight * 100)}% target`; const amount = document.createElement('strong'); amount.textContent = money(item.target); row.append(label, amount); allocation.appendChild(row); });
      const rec = $('recommendation'); rec.replaceChildren(); data.recommendations.forEach(message => { const p = document.createElement('p'); p.textContent = message; p.style.margin = '9px 0'; rec.appendChild(p); });
      if (trip && trip.query) { const linked = document.createElement('p'); linked.textContent = 'Trip context used: ' + trip.query; linked.style.marginTop = '10px'; rec.appendChild(linked); }
      $('disclaimer').textContent = data.disclaimer; results.hidden = false;
    } catch (err) { error.textContent = err.message || 'Unexpected error.'; error.hidden = false; }
  });
})();
