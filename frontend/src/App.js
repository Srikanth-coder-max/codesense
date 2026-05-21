import React, { useState } from 'react';
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

  // --- Updated Handler for /ingest ---
  const handleIngest = async (e) => {
    e.preventDefault();
    if (!githubUrl.trim()) return;

    setIsIngesting(true);
    setIngestStatus('Cloning and building vector DB (this may take a moment)...');

    try {
      const response = await fetch(`${API_BASE_URL}/api/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: githubUrl }),
      });

      if (response.ok) {
        setIngestStatus('Repo ready! You can now ask questions.');
      } else {
        const errorData = await response.json();
        setIngestStatus(`Error: ${errorData.detail || 'Failed to process repo'}`);
      }
    } catch (error) {
      console.error("Ingest error:", error);
      setIngestStatus('Network error connecting to backend.');
    } finally {
      setIsIngesting(false);
    }
  };

  // --- Updated Handler for /ask ---
  const handleAsk = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setAnswer(''); 

    try {
      const response = await fetch(`${API_BASE_URL}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n").filter(line => line.startsWith("data: "));

        for (const line of lines) {
          const data = line.replace("data: ", "").trim();
          
          if (data === "[DONE]") {
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
    } catch (error) {
      console.error("Streaming error:", error);
      setAnswer("An error occurred while fetching the response.");
    } finally {
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