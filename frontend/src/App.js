import React, { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

// API routing strategy:
//  - PRODUCTION (Vercel): always use a relative base ("") so that fetch("/api/ingest")
//    is handled by the vercel.json rewrite rule, which proxies it securely to EC2.
//    This means the raw EC2 IP is NEVER exposed to the browser.
//  - LOCAL DEV: reads REACT_APP_API_URL from your .env.local file so you can point
//    directly at http://localhost:8000 without touching vercel.json.
const API_BASE_URL =
  process.env.NODE_ENV === "production"
    ? ""
    : (process.env.REACT_APP_API_URL || "http://localhost:8000");


function App() {
  // --- New States for GitHub Ingestion ---
  const [githubUrl, setGithubUrl] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState('');

  // --- Existing States for Q&A ---
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // --- Refs for synchronous lock protection ---
  // React state updates (setIsLoading) are asynchronous. If a user holds down
  // the Enter key, multiple submits can fire before the button disables.
  // These refs prevent duplicate concurrent requests.
  const isIngestingRef = useRef(false);
  const isLoadingRef = useRef(false);

  // --- Updated Handler for /ingest (async polling pattern) ---
  const handleIngest = async (e) => {
    e.preventDefault();
    if (isIngestingRef.current || !githubUrl.trim()) return;

    isIngestingRef.current = true;
    setIsIngesting(true);
    setIngestStatus('Submitting repository...');

    try {
      // Phase 1: POST to kick off the job — returns 202 + job_id immediately.
      // This call completes in <1s so Vercel's proxy timeout is never hit.
      const submitRes = await fetch(`${API_BASE_URL}/api/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: githubUrl }),
      });

      if (!submitRes.ok) {
        const err = await submitRes.json();
        setIngestStatus(`Error: ${err.detail || 'Failed to start ingestion.'}`);
        isIngestingRef.current = false;
        setIsIngesting(false);
        return;
      }

      const { job_id } = await submitRes.json();
      setIngestStatus('Cloning repo and building knowledge base… (this takes 1–3 minutes for large repos)');

      // Phase 2: Poll GET /api/ingest/status/{job_id} every 3 seconds.
      const poll = setInterval(async () => {
        try {
          const statusRes = await fetch(`${API_BASE_URL}/api/ingest/status/${job_id}`);
          const data = await statusRes.json();

          if (data.status === 'running') {
            setIngestStatus('⚙️ Embedding code chunks into vector database…');
          } else if (data.status === 'complete') {
            clearInterval(poll);
            setIngestStatus('✅ Repo ready! You can now ask questions.');
            isIngestingRef.current = false;
            setIsIngesting(false);
          } else if (data.status === 'failed') {
            clearInterval(poll);
            setIngestStatus(`❌ Error: ${data.detail || 'Ingestion failed.'}`);
            isIngestingRef.current = false;
            setIsIngesting(false);
          }
          // 'pending' → keep polling silently
        } catch (pollErr) {
          console.error("Polling error:", pollErr);
          // Network hiccup — keep polling, don't abort
        }
      }, 3000);

    } catch (error) {
      console.error("Ingest submit error:", error);
      setIngestStatus('❌ Network error connecting to backend.');
      isIngestingRef.current = false;
      setIsIngesting(false);
    }
  };


  // --- Updated Handler for /ask ---
  const handleAsk = async (e) => {
    e.preventDefault();
    if (isLoadingRef.current || !query.trim()) return;

    isLoadingRef.current = true;
    setIsLoading(true);
    setAnswer(''); 

    try {
      const response = await fetch(`${API_BASE_URL}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // Split on newlines, keeping the last incomplete line in the buffer
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            
            if (data === "[DONE]") {
              isLoadingRef.current = false;
              setIsLoading(false);
              return;
            }

            try {
              const parsed = JSON.parse(data);
              if (parsed.token) {
                setAnswer(prev => prev + parsed.token);
              }
            } catch (err) {
              console.error("Error parsing JSON chunk:", err, data);
            }
          }
        }
      }
    } catch (error) {
      console.error("Streaming error:", error);
      setAnswer("An error occurred while fetching the response.");
    } finally {
      isLoadingRef.current = false;
      setIsLoading(false);
    }
  };

  return (
    <div className="app-root">
      <header className="app-hero">
        <div className="app-hero-inner">
          <h1 className="brand">CodeSense</h1>
          <p className="subtitle">Explore and ask questions about your codebase</p>
        </div>
      </header>

      <main className="app-container">
        <div className="left-col">
          <div className="card">
            <h2 className="card-title">Load Repository</h2>
            <form onSubmit={handleIngest} className="form-row">
              <input
                className="input"
                type="text"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/username/repo"
                disabled={isIngesting}
              />
              <button className="btn primary" type="submit" disabled={isIngesting || !githubUrl.trim()}>
                {isIngesting ? 'Loading...' : 'Load Repo'}
              </button>
            </form>
            {ingestStatus && <p className="status">{ingestStatus}</p>}
          </div>

          <div className="card small">
            <h3 className="card-title">Tips</h3>
            <ul className="tips">
              <li>Paste a GitHub repo URL to index its code.</li>
              <li>Once ingested, ask natural language questions.</li>
            </ul>
          </div>
        </div>

        <div className="right-col">
          <div className="card">
            <h2 className="card-title">Ask Codebase</h2>
            <form onSubmit={handleAsk} className="form-row">
              <input
                className="input"
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask a question about your codebase..."
                disabled={isLoading}
              />
              <button className="btn accent" type="submit" disabled={isLoading || !query.trim()}>
                {isLoading ? 'Searching...' : 'Ask'}
              </button>
            </form>

            <div className="result-card">
              {answer ? (
                <div className="markdown-output"><ReactMarkdown>{answer}</ReactMarkdown></div>
              ) : isLoading ? (
                <div className="loader" aria-hidden>Searching…</div>
              ) : (
                <div className="empty">The streamed response will appear here.</div>
              )}
            </div>

            {answer && !isLoading && (
              <div className="row-right">
                <button className="btn ghost" onClick={() => { setAnswer(''); setQuery(''); }}>
                  Clear
                </button>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="app-footer">Built with ❤️ — CodeSense</footer>
    </div>
  );
}

export default App;