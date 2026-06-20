import React, { useState, useRef, useEffect } from 'react';

function formatMarkdown(text) {
  if (!text) return null;
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*\*.*?\*\*)/g);
    const formattedLine = parts.map((part, j) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={j} style={{ color: 'var(--navy)' }}>{part.slice(2, -2)}</strong>;
      }
      return <span key={j}>{part}</span>;
    });
    return <div key={i} style={{ marginBottom: 6 }}>{formattedLine}</div>;
  });
}

export default function ChatbotWidget({ api }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Ready to assist, Commander. Ask me about today\'s high-risk junctions or deployment strategies.' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch(`${api}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });
      const data = await response.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply || "Error: No reply" }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠ API Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{
          position: 'fixed', bottom: 24, right: 24,
          width: 60, height: 60, borderRadius: 30,
          background: 'linear-gradient(135deg, #0e2a4d, #1a3f6f)',
          color: '#fff', border: 'none',
          boxShadow: '0 8px 24px rgba(26,63,111,0.4)',
          fontSize: 28, cursor: 'pointer', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'transform 0.2s',
        }}
      >
        ✨
      </button>
    );
  }

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24,
      width: 380, height: 500, borderRadius: 16,
      background: '#f8fafc', boxShadow: '0 12px 48px rgba(0,0,0,0.15)',
      display: 'flex', flexDirection: 'column', zIndex: 9999,
      overflow: 'hidden', border: '1px solid #d0dae8'
    }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(90deg, #0e2a4d, #1a3f6f)',
        color: '#fff', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ background: '#fff', borderRadius: '50%', width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>🤖</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.5 }}>ASTraM Copilot</div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.7)' }}>Live Intelligence Mode</div>
          </div>
        </div>
        <button onClick={() => setIsOpen(false)} style={{ background: 'none', border: 'none', color: '#fff', fontSize: 18, cursor: 'pointer' }}>✖</button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: 'flex', gap: 12, justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {m.role === 'assistant' && (
              <div style={{ width: 28, height: 28, background: 'linear-gradient(135deg, #10b981, #059669)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: '#fff', flexShrink: 0 }}>🤖</div>
            )}
            <div style={{
              background: m.role === 'user' ? 'var(--navy)' : '#fff',
              color: m.role === 'user' ? '#fff' : 'var(--text-1)',
              padding: '12px 16px', border: m.role === 'user' ? 'none' : '1px solid #e2e8f0',
              borderRadius: m.role === 'user' ? '16px 16px 0 16px' : '0 16px 16px 16px',
              fontSize: 13, lineHeight: 1.5, maxWidth: '85%',
              boxShadow: m.role === 'user' ? 'none' : '0 2px 4px rgba(0,0,0,0.02)'
            }}>
              {m.role === 'assistant' ? formatMarkdown(m.content) : m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ width: 28, height: 28, background: 'linear-gradient(135deg, #10b981, #059669)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: '#fff', flexShrink: 0 }}>🤖</div>
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', padding: '12px 16px', borderRadius: '0 16px 16px 16px', fontSize: 13, color: 'var(--text-3)' }}>
              <span className="typing-dots">Analyzing...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <div style={{ padding: '16px 20px', background: '#fff', borderTop: '1px solid #e2e8f0' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder="Ask about junctions or deployment..."
            style={{
              flex: 1, padding: '10px 16px', borderRadius: 24, border: '1px solid #cbd5e1',
              fontSize: 13, outline: 'none'
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              background: loading || !input.trim() ? '#94a3b8' : 'var(--navy)',
              color: '#fff', border: 'none', borderRadius: 24, padding: '0 16px',
              fontWeight: 600, cursor: loading || !input.trim() ? 'not-allowed' : 'pointer'
            }}
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}
