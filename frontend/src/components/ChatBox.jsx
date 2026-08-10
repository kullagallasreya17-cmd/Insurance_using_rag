import { useEffect, useRef, useState } from "react";
import api from "../api";
import "./ChatBox.css";

const SUGGESTED_QUESTIONS = [
  "Is knee surgery covered?",
  "Summarize my policy.",
  "Explain Clause 4.2.",
  "What is my waiting period?",
];

const PLACEHOLDER_TEXTS = [
  "Ask about your insurance policy, medical report, hospital bill, or claim...",
  "Is this treatment covered?",
  "What documents do I need?",
  "Explain my policy exclusions.",
];

const QUICK_ACTIONS = [
  { label: "Summarize Policy", icon: "📄" },
  { label: "Check Coverage", icon: "🩺" },
  { label: "Explain Clause", icon: "📖" },
  { label: "Claim Eligibility", icon: "📋" },
];

const THINKING_STEPS = [
  "Searching policy documents...",
  "Analyzing medical reports...",
  "Retrieving relevant clauses...",
  "Generating response...",
];
const CHAT_HISTORY_KEY = "insurance_ai_chat_history_v1";

function loadStoredChatHistory() {
  try {
    const stored = localStorage.getItem(CHAT_HISTORY_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error("Failed to load saved chat history", error);
    return [];
  }
}

function ChatBox() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState(() => loadStoredChatHistory());
  const [currentChatId, setCurrentChatId] = useState(null);
  const [currentChatTitle, setCurrentChatTitle] = useState("New Chat");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [thinkingStep, setThinkingStep] = useState(0);
  const chatEndRef = useRef(null);
  const thinkingIntervalRef = useRef(null);
  const placeholderIntervalRef = useRef(null);
  const [stats, setStats] = useState({
    policiesIndexed: 0,
    reportsIndexed: 0,
    conversationCount: 0,
  });
  const [aiStatus, setAiStatus] = useState("ready");

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    placeholderIntervalRef.current = window.setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDER_TEXTS.length);
    }, 4000);

    return () => window.clearInterval(placeholderIntervalRef.current);
  }, []);

  useEffect(() => {
    if (loading) {
      setThinkingStep(0);
      thinkingIntervalRef.current = window.setInterval(() => {
        setThinkingStep((prev) => (prev + 1) % THINKING_STEPS.length);
      }, 1200);
      setAiStatus("thinking");
    } else {
      window.clearInterval(thinkingIntervalRef.current);
      setAiStatus("ready");
    }

    return () => window.clearInterval(thinkingIntervalRef.current);
  }, [loading]);

  useEffect(() => {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
  }, [chatHistory]);

  useEffect(() => {
    const loadDocumentStats = async () => {
      try {
        const docsResponse = await api.get("/documents");
        const docs = docsResponse.data.documents || [];
        const policies = docs.filter((d) => d.document_type === "policy").length;
        const reports = docs.filter((d) => d.document_type !== "policy").length;
        setStats((prev) => ({
          ...prev,
          policiesIndexed: policies,
          reportsIndexed: reports,
          conversationCount: chatHistory.length,
        }));
      } catch (error) {
        console.error("Failed to load document stats", error);
      }
    };

    loadDocumentStats();
  }, [chatHistory]);

  const generateChatTitle = (firstQuestion) => {
    const words = firstQuestion.split(" ").slice(0, 3).join(" ");
    return words.length > 0 ? words : "Conversation";
  };

  const startNewChat = () => {
    setMessages([]);
    setQuestion("");
    setCurrentChatId(null);
    setCurrentChatTitle("New Chat");
  };

  const loadChat = (chatId) => {
    const chat = chatHistory.find((c) => c.id === chatId);
    if (chat) {
      setCurrentChatId(chatId);
      setMessages(chat.messages);
      setCurrentChatTitle(chat.title);
    }
  };

  const sendMessage = async () => {
    if (!question.trim()) return;

    const userMessage = {
      sender: "user",
      text: question,
      timestamp: new Date().toLocaleTimeString(),
    };

    let newMessages = [...messages, userMessage];
    setMessages(newMessages);

    if (!currentChatId && messages.length === 0) {
      const newChatId = `chat_${Date.now()}`;
      const title = generateChatTitle(question);
      setCurrentChatId(newChatId);
      setCurrentChatTitle(title);
    }

    setQuestion("");
    setLoading(true);

    const startTime = Date.now();

    try {
      const response = await api.post("/chat", { question: question });
      const responseTime = ((Date.now() - startTime) / 1000).toFixed(2);

      const aiMessage = {
        sender: "ai",
        text: response.data.answer,
        sources: response.data.sources || [],
        timestamp: new Date().toLocaleTimeString(),
        responseTime: parseFloat(responseTime),
      };

      newMessages = [...newMessages, aiMessage];
      setMessages(newMessages);



      if (currentChatId) {
        setChatHistory((prev) =>
          prev.map((chat) =>
            chat.id === currentChatId
              ? { ...chat, messages: newMessages, lastUpdated: new Date() }
              : chat
          )
        );
      } else {
        const newChatId = `chat_${Date.now()}`;
        setChatHistory((prev) => [
          {
            id: newChatId,
            title: currentChatTitle,
            messages: newMessages,
            lastUpdated: new Date(),
          },
          ...prev,
        ]);
        setCurrentChatId(newChatId);
      }
    } catch (error) {
      console.error(error);

      const errorMessage = {
        sender: "ai",
        text: "Something went wrong while contacting the server.",
        timestamp: new Date().toLocaleTimeString(),
      };

      newMessages = [...newMessages, errorMessage];
      setMessages(newMessages);
    }

    setLoading(false);
  };

  const handleSuggestedQuestion = (suggestedQuestion) => {
    setQuestion(suggestedQuestion);
  };

  const handleQuickAction = (action) => {
    setQuestion(action);
  };

  const groupHistoryByDate = () => {
    const grouped = {};
    const today = new Date().toLocaleDateString();
    const yesterday = new Date(Date.now() - 86400000).toLocaleDateString();

    chatHistory.forEach((chat) => {
      const chatDate = new Date(chat.lastUpdated).toLocaleDateString();
      let groupLabel;

      if (chatDate === today) groupLabel = "Today";
      else if (chatDate === yesterday) groupLabel = "Yesterday";
      else groupLabel = chatDate;

      if (!grouped[groupLabel]) grouped[groupLabel] = [];
      grouped[groupLabel].push(chat);
    });

    return grouped;
  };

  const renderMessageContent = (msg) => {
    if (msg.sender === "user") {
      return (
        <div className="message-bubble user-bubble">
          <div className="message-content">
            <p>{msg.text}</p>
            <span className="message-time">{msg.timestamp}</span>
          </div>
        </div>
      );
    }

    const sourceList = msg.sources || msg.citations || [];
    const normalizedSources = sourceList.map((source) => {
      if (typeof source === "string") return source;
      return `${source.source || "Unknown source"}${source.page ? ` • Page ${source.page}` : ""}`;
    });

    return (
      <div className="message-bubble ai-bubble">
        <div className="message-content">
          <p>{msg.text}</p>

          {normalizedSources.length > 0 && (
            <div className="sources-panel">
              <strong>📄 Sources Used:</strong>
              <ul>
                {normalizedSources.map((source, idx) => (
                  <li key={idx}>
                    <span>{source}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <span className="message-time">⏱️ {msg.responseTime || 0}s</span>
        </div>
      </div>
    );
  };

  const groupedHistory = groupHistoryByDate();

  return (
    <div className="chatbox-layout">
      <div className="chat-sidebar">
        <button className="new-chat-btn" onClick={startNewChat}>
          + New Chat
        </button>

        <div className="sidebar-section">
          <h3>💬 Chat History</h3>
          <div className="history-list">
            {chatHistory.length === 0 ? (
              <p className="empty-state">No chats yet. Start a conversation!</p>
            ) : (
              Object.entries(groupedHistory).map(([date, chats]) => (
                <div key={date} className="history-group">
                  <p className="history-date">{date}</p>
                  {chats.map((chat) => (
                    <div
                      key={chat.id}
                      className={`history-item ${currentChatId === chat.id ? "active" : ""}`}
                      onClick={() => loadChat(chat.id)}
                    >
                      <span>🗨️</span>
                      <p title={chat.title}>{chat.title}</p>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>📊 Statistics</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-label">Policies Indexed</span>
              <span className="stat-value">{stats.policiesIndexed}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Reports Indexed</span>
              <span className="stat-value">{stats.reportsIndexed}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Conversations</span>
              <span className="stat-value">{chatHistory.length}</span>
            </div>

          </div>
        </div>
      </div>

      <div className="chat-container">
        <div className="chat-header">
          🛡️ Insurance AI Assistant
          <span className="header-subtitle">Powered by RAG + Gemini AI</span>
          <span className={`ai-status status-${aiStatus}`}>
            {aiStatus === "ready" ? "🟢" : "🟡"} {aiStatus === "ready" ? "AI Ready" : "AI Thinking"}
            {stats.policiesIndexed > 0 && ` • ${stats.policiesIndexed} Documents`}
          </span>
        </div>

        <div className="chat-upload-shortcuts">
          <a href="/upload-policy" className="shortcut-btn">📄 Upload Policy</a>
          <a href="/documents" className="shortcut-btn">🏥 Medical Report</a>
          <a href="/documents" className="shortcut-btn">🧾 Hospital Bill</a>
        </div>

        <div className="chat-body">
          {messages.length === 0 && (
            <div className="welcome-section">
              <h2>👋 Welcome to Insurance AI</h2>
              <p>Ask any question about your insurance policy, medical reports, or claims.</p>

              <div className="suggestions-section">
                <h4>💡 Try Asking:</h4>
                <div className="suggestions-grid">
                  {SUGGESTED_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      className="suggestion-btn"
                      onClick={() => handleSuggestedQuestion(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>

              <div className="quick-actions-section">
                <h4>⚡ Quick Actions:</h4>
                <div className="quick-actions-grid">
                  {QUICK_ACTIONS.map((action, idx) => (
                    <button
                      key={idx}
                      className="quick-action-btn"
                      onClick={() => handleQuickAction(action.label)}
                    >
                      {action.icon} {action.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, index) => (
            <div key={index} className="message-wrapper">
              {msg.sender === "user" && <div className="message-avatar user-avatar">👤</div>}
              {msg.sender === "ai" && <div className="message-avatar ai-avatar">🤖</div>}
              {renderMessageContent(msg)}
            </div>
          ))}

          {loading && (
            <div className="thinking-animation">
              <div className="spinner"></div>
              <p>{THINKING_STEPS[thinkingStep]}</p>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        <div className="chat-footer">
          <input
            type="text"
            placeholder={PLACEHOLDER_TEXTS[placeholderIndex]}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !loading) {
                sendMessage();
              }
            }}
            disabled={loading}
          />
          <button onClick={sendMessage} disabled={loading}>
            {loading ? "⏳" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatBox;
