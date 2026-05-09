const http = require('http');

http.get('http://localhost:3000', (res) => {
  let chunks = [];
  res.on('data', c => chunks.push(c));
  res.on('end', () => {
    const html = Buffer.concat(chunks).toString();
    console.log("HTML length:", html.length);
    // Find next.js errors
    if (html.includes("Unhandled Runtime Error") || html.includes("Next.js Error") || html.includes("Hydration")) {
      console.log("Found error block:", html.substring(html.indexOf("error"), html.indexOf("error") + 200));
    } else {
      console.log("No React runtime errors found in html text.");
    }
    // Print a few lines of where the header is
    const idx = html.indexOf("Pulps &amp; Leaves");
    if (idx !== -1) {
      console.log("Found header around:", html.substring(Math.max(0, idx - 100), idx + 200));
    }
  });
}).on('error', err => console.log("Fetch error:", err.message));
