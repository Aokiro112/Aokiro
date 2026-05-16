// @ts-nocheck
import React, { useState, useEffect, useCallback } from 'react';
import { Socket } from 'socket.io-client';
import MessageBubble from './MessageBubble';
import { useAuth } from '../hooks/useAuth';

export const ChatBox = ({ roomId }) => {
  const [messages, setMessages] = useState([]);
  const { user } = useAuth();

  const handleMsg = useCallback((msg) => {
    setMessages(prev => [...prev, msg]);
  }, []);

  useEffect(() => {
    const socket = new Socket('http://localhost:3000');
    socket.emit('join', roomId);
    socket.on('message', handleMsg);
    
    return () => {
      socket.off('message', handleMsg);
      socket.disconnect();
    }
  }, [roomId, handleMsg]);

  if (!user) return <AuthPrompt />;

  return (
    <div className="chat-container">
      <Header title={`Room ${roomId}`} />
      <div className="messages-list">
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>
      <ChatInput onSend={(text) => console.log(text)} />
    </div>
  );
};

export default ChatBox;
