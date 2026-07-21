import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { embeddedId } = await req.json();

    if (!embeddedId) {
      return NextResponse.json({ error: "Missing embeddedId" }, { status: 400 });
    }

    // 🔴 IMPORTANT: FILL IN YOUR SUPERSET DETAILS HERE
    // You can also put these inside a .env.local file in your Next.js project
    const SUPERSET_URL = process.env.SUPERSET_URL || "http://localhost:8088"; 
    const SUPERSET_USERNAME = process.env.SUPERSET_USERNAME || "admin";
    const SUPERSET_PASSWORD = process.env.SUPERSET_PASSWORD || "admin";
    
    // Step 1: Login to get the Admin Access Token
    const loginRes = await fetch(`${SUPERSET_URL}/api/v1/security/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: SUPERSET_USERNAME,
        password: SUPERSET_PASSWORD,
        provider: "db" // Usually 'db' or 'ldap' depending on your setup
      })
    });

    if (!loginRes.ok) {
      const errText = await loginRes.text();
      console.error("Superset login failed:", errText);
      return NextResponse.json({ error: "Failed to authenticate with Superset backend." }, { status: 500 });
    }

    const { access_token } = await loginRes.json();
    
    // Extract the session cookie securely
    let sessionCookie = "";
    if (typeof loginRes.headers.getSetCookie === 'function') {
      const cookies = loginRes.headers.getSetCookie();
      const session = cookies.find(c => c.startsWith('session='));
      if (session) sessionCookie = session.split(';')[0];
    } else {
      const setCookieHeader = loginRes.headers.get("set-cookie");
      if (setCookieHeader) {
        const match = setCookieHeader.match(/session=([^;]+)/);
        if (match) sessionCookie = match[0];
      }
    }

    // Step 1.5: Fetch the CSRF Token
    const csrfRes = await fetch(`${SUPERSET_URL}/api/v1/security/csrf_token/`, {
      headers: {
        Authorization: `Bearer ${access_token}`,
        Cookie: sessionCookie
      }
    });
    
    let csrfToken = "";
    if (csrfRes.ok) {
      const csrfData = await csrfRes.json();
      csrfToken = csrfData.result;
      
      // Update session cookie if Superset rotated it during CSRF generation
      if (typeof csrfRes.headers.getSetCookie === 'function') {
        const newCookies = csrfRes.headers.getSetCookie();
        const newSession = newCookies.find(c => c.startsWith('session='));
        if (newSession) sessionCookie = newSession.split(';')[0];
      } else {
        const newCookieHeader = csrfRes.headers.get("set-cookie");
        if (newCookieHeader) {
          const match = newCookieHeader.match(/session=([^;]+)/);
          if (match) sessionCookie = match[0];
        }
      }
    }

    // Step 2: Request the Guest Token for the specific embedded dashboard
    const guestTokenRes = await fetch(`${SUPERSET_URL}/api/v1/security/guest_token/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${access_token}`,
        Cookie: sessionCookie,
        "X-CSRFToken": csrfToken,
        Referer: SUPERSET_URL // Required by flask_wtf strict mode
      },
      body: JSON.stringify({
        user: {
          username: "sprint_dss_viewer", // A dummy username for the guest
          first_name: "Sprint",
          last_name: "Viewer",
        },
        resources: [{ type: "dashboard", id: embeddedId }],
        rls: [] // Row Level Security rules (leave empty to show all data, or add filters)
      })
    });

    if (!guestTokenRes.ok) {
      const errText = await guestTokenRes.text();
      console.error("Failed to fetch guest token:", errText);
      return NextResponse.json({ error: "Failed to fetch guest token from Superset", details: errText }, { status: 500 });
    }

    const { token } = await guestTokenRes.json();

    // Step 3: Return the guest token securely to the frontend
    return NextResponse.json({ token });
  } catch (error: any) {
    console.error("Superset API Error:", error);
    return NextResponse.json({ error: error.message || "Internal Server Error" }, { status: 500 });
  }
}
