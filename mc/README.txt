Jacob Hart Minecraft page redesign

This ZIP is arranged to match your repository paths:
- mc/index.html: replacement for the existing Minecraft page
- functions/api/status.js: replacement for the repository-root Pages Function

To apply:
1. Extract this ZIP into your jacobhart.me repository folder, keeping the folder layout.
2. Replace the existing mc/index.html and repository-root functions/api/status.js with these files.
3. Commit and push both changes, then wait for Cloudflare Pages to deploy.

The status function retains the Service Binding, 15-second Cloudflare cache, GET-only API route, 8-second upstream timeout, and response validation. It adds CORS headers because the Minecraft page fetches the test API on a different hostname.

The page currently reads https://jacobhart-me-pages-test.pages.dev/api/status. This is the working test API URL. Change API_URL in mc/index.html only when the production API URL is ready.

The Bedrock card displays port 20338 based on the configured connection information available when the page was prepared. Verify it still matches the current tunnel settings before relying on it.
