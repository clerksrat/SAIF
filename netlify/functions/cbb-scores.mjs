// Live and final scores for the college basketball board, from CollegeBasketballData.
// GET /api/cbb-scores?date=2026-11-02  ->  { date, updated, games: [{ id, hp, ap, status }] }
// `date` is the board's Eastern date; games are matched on the page by CBBD game id.
// Same key as football (CFBD_API_KEY in Netlify, Functions scope). Cached on Netlify's CDN for
// 10 minutes per date, so every visitor shares one call against the CFBD/CBBD quota.

export default async (req) => {
  const date = new URL(req.url).searchParams.get('date') || '';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return Response.json({ error: 'date=YYYY-MM-DD required' }, { status: 400 });
  }
  const key = Netlify.env.get('CFBD_API_KEY');
  if (!key) return Response.json({ error: 'CFBD_API_KEY is not set in Netlify' }, { status: 500 });

  // An Eastern-time day runs from 04:00/05:00 UTC to 04:00/05:00 UTC the next day; take a wide UTC window.
  const d = new Date(date + 'T00:00:00Z');
  const next = new Date(d.getTime() + 2 * 86400000).toISOString().slice(0, 10);
  const season = d.getUTCMonth() >= 7 ? d.getUTCFullYear() + 1 : d.getUTCFullYear();   // 2026-11 -> 2027
  const url = `https://api.collegebasketballdata.com/games?season=${season}` +
    `&startDateRange=${date}T00:00:00Z&endDateRange=${next}T00:00:00Z`;

  let games;
  try {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' } });
    if (!r.ok) {
      return Response.json({ error: `CBBD returned ${r.status}` }, {
        status: 502,
        headers: { 'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=120', 'Netlify-Vary': 'query=date' },
      });
    }
    games = await r.json();
  } catch (err) {
    return Response.json({ error: 'CBBD unreachable' }, { status: 502 });
  }

  const out = games
    .filter((g) => g.status === 'final' || g.status === 'in_progress')
    .map((g) => ({ id: g.id, hp: g.homePoints, ap: g.awayPoints, status: g.status }));

  return Response.json({ date, updated: new Date().toISOString(), games: out }, {
    headers: {
      'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=600, stale-while-revalidate=120',
      'Cache-Control': 'public, max-age=60',
      'Netlify-Vary': 'query=date',
    },
  });
};

export const config = { path: '/api/cbb-scores', method: 'GET' };
