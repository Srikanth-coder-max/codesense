import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

function App() {
  // --- New States for GitHub Ingestion ---
  const [githubUrl, setGithubUrl] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState('');

  // --- Existing States for Q&A ---
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // --- New Handler for /ingest ---
  const handleIngest = async (e) => {
    e.preventDefault();
    if (!githubUrl.trim()) return;

    setIsIngesting(true);
    setIngestStatus('Cloning and building vector DB (this may take a moment)...');

    try {
      const response = await fetch("http://15.134.143.250:8000/ingest", {
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

  // --- Existing Handler for /ask ---
  const handleAsk = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setAnswer(''); 

    try {
      const response = await fetch("http://15.134.143.250:8000/ask", {
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
    <div style={{ maxWidth: '800px', margin: '50px auto', fontFamily: 'sans-serif' }}>
      <h1>CodeSense</h1>
      
      {/* --- Step 1: Ingest Repo UI --- */}
      <div style={{ background: '#f1f3f5', padding: '15px', borderRadius: '8px', marginBottom: '30px' }}>
        <h3>1. Load Repository</h3>
        <form onSubmit={handleIngest} style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            placeholder="https://github.com/username/repo"
            style={{ flex: 1, padding: '10px', fontSize: '15px', borderRadius: '4px', border: '1px solid #ccc' }}
            disabled={isIngesting}
          />
          <button 
            type="submit" 
            disabled={isIngesting || !githubUrl.trim()} 
            style={{ padding: '10px 20px', cursor: 'pointer', borderRadius: '4px', background: '#28a745', color: 'white', border: 'none' }}
          >
            {isIngesting ? 'Loading...' : 'Load Repo'}
          </button>
        </form>
        {ingestStatus && <p style={{ marginTop: '10px', fontSize: '14px', fontWeight: 'bold' }}>{ingestStatus}</p>}
      </div>

      {/* --- Step 2: Ask Questions UI --- */}
      <h3>2. Ask Codebase</h3>
      <form onSubmit={handleAsk} style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about your codebase..."
          style={{ flex: 1, padding: '12px', fontSize: '16px', borderRadius: '4px', border: '1px solid #ccc' }}
          disabled={isLoading}
        />
        <button 
          type="submit" 
          disabled={isLoading || !query.trim()} 
          style={{ padding: '12px 24px', fontSize: '16px', cursor: 'pointer', borderRadius: '4px', background: '#007bff', color: 'white', border: 'none' }}
        >
          {isLoading ? 'Searching...' : 'Ask'}
        </button>
      </form>

      {/* --- Results Display --- */}
      <div style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', minHeight: '150px', border: '1px solid #e9ecef' }}>
        {answer ? (
          <ReactMarkdown>{answer}</ReactMarkdown>
        ) : isLoading ? (
          <span style={{ color: '#6c757d', fontSize: '20px' }}>▋</span>
        ) : (
          <p style={{ color: '#6c757d', margin: 0 }}>The response will stream here...</p>
        )}
      </div>

      {answer && !isLoading && (
        <button
          onClick={() => { setAnswer(''); setQuery(''); }}
          style={{ marginTop: '12px', padding: '6px 14px', cursor: 'pointer', borderRadius: '4px', background: 'transparent', border: '1px solid #ccc', color: '#6c757d', fontSize: '14px' }}
        >
          Clear
        </button>
      )}
    </div>
  );
}

export default App;