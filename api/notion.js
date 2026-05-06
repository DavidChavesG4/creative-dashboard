export const config = { runtime: 'edge' };

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type, Notion-Version',
      }
    });
  }

  const url = new URL(req.url);
  const notionPath = url.searchParams.get('path') || '/v1/users/me';
  const notionUrl = `https://api.notion.com${notionPath}`;

  const headers = {
    'Authorization': req.headers.get('Authorization') || '',
    'Notion-Version': req.headers.get('Notion-Version') || '2022-06-28',
    'Content-Type': 'application/json',
  };

  const body = req.method !== 'GET' ? await req.text() : undefined;

  const resp = await fetch(notionUrl, {
    method: req.method,
    headers,
    body
  });

  const data = await resp.text();

  return new Response(data, {
    status: resp.status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type, Notion-Version',
    }
  });
}
