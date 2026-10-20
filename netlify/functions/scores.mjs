// Week's final scores for the board, from CollegeFootballData.
// GET /api/scores?year=2026&week=8  ->  { year, week, updated, games: [{ id, home, away, hp, ap, done }] }
// The CFBD key lives in the Netlify environment variable CFBD_API_KEY (scope: Functions), never in the page.
// Responses are cached on Netlify's CDN for 10 minutes per year/week, so every visitor shares one CFBD call.

export default async (req) => {
  const q = new URL(req.url).searchParams;
  const year = Number(q.get('year'));
  const week = Number(q.get('week'));
  if (!Number.isInteger(year) || year < 2020 || year > 2100 || !Number.isInteger(week) || week < 1 || week > 20) {
    return Response.json({ error: 'year and week required' }, { status: 400 });
  }

  const key = Netlify.env.get('CFBD_API_KEY');
  if (!key) {
    return Response.json({ error: 'CFBD_API_KEY is not set in Netlify' }, { status: 500 });
  }

  let games;
  try {
    const r = await fetch(
      `https://api.collegefootballdata.com/games?year=${year}&week=${week}&seasonType=regular`,
      { headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' } },
    );
    if (!r.ok) {
      // short cache so an outage or rate limit doesn't turn every page view into another CFBD call
      return Response.json({ error: `CFBD returned ${r.status}` }, {
        status: 502,
        headers: { 'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=120', 'Netlify-Vary': 'query=year|week' },
      });
    }
    games = await r.json();
  } catch (err) {
    return Response.json({ error: 'CFBD unreachable' }, { status: 502 });
  }

  const out = games
    .filter((g) => g.homePoints != null && g.awayPoints != null)
    .map((g) => ({ id: g.id, home: g.homeTeam, away: g.awayTeam, hp: g.homePoints, ap: g.awayPoints, done: g.completed === true }));

  return Response.json({ year, week, updated: new Date().toISOString(), games: out }, {
    headers: {
      'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=600, stale-while-revalidate=120',
      'Cache-Control': 'public, max-age=60',
      'Netlify-Vary': 'query=year|week',
    },
  });
};

export const config = { path: '/api/scores', method: 'GET' };
