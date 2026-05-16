const fs = require('fs');
const path = require('path');

const files = {
  'BuggyMemoryLeak.tsx': `
import React, { useEffect } from 'react';
export const MemoryLeak = () => {
  useEffect(() => {
    window.addEventListener('resize', () => console.log('resize'));
    // Missing cleanup
  }, []);
  return <div>Leak</div>;
};
  `,
  'BuggyStaleClosure.tsx': `
import React, { useState, useEffect } from 'react';
export function Counter() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setCount(count + 1); // Stale closure
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return <div>{count}</div>;
}
  `,
  'ArchitectureMonolith.tsx': `
import React, { useState, useEffect } from 'react';
import axios from 'axios';
export const Monolith = () => {
  const [data, setData] = useState(null);
  const [user, setUser] = useState(null);
  const [isOpen, setIsOpen] = useState(false);
  
  useEffect(() => {
    axios.get('/api/data').then(res => setData(res.data));
    axios.get('/api/user').then(res => setUser(res.data));
  }, []);

  return (
    <div className="giant">
      <header>Welcome {user?.name}</header>
      <main>
         {data?.map(d => <div key={d.id}>{d.title}</div>)}
         <button onClick={() => setIsOpen(true)}>Open Modal</button>
         {isOpen && <div className="modal">Settings... <button onClick={() => setIsOpen(false)}>Close</button></div>}
      </main>
    </div>
  );
};
  `,
  'PropDrilling.tsx': `
import React from 'react';
import { GrandChild } from './GrandChild';
export const Parent = ({ user, theme, onUpdate, settings, features }) => {
  return (
    <div>
      <Child user={user} theme={theme} onUpdate={onUpdate} settings={settings} features={features} />
    </div>
  );
};
  `,
  'CleanHook.tsx': `
import { useState, useCallback } from 'react';
export function useToggle(initialValue = false) {
  const [value, setValue] = useState(initialValue);
  const toggle = useCallback(() => setValue(v => !v), []);
  return [value, toggle];
}
  `,
  'ComplexComponent.tsx': `
import React, { useMemo } from 'react';
import { useToggle } from './CleanHook';
import { Header } from './Header';
export const Complex = ({ items }) => {
  const [isOpen, toggle] = useToggle();
  const sorted = useMemo(() => items.sort(), [items]);
  return (
    <div>
      <Header isOpen={isOpen} onToggle={toggle} />
      <ul>{sorted.map(i => <li key={i}>{i}</li>)}</ul>
    </div>
  );
};
  `,
  'MissingDeps.tsx': `
import React, { useEffect, useState } from 'react';
export const UserProfile = ({ userId }) => {
  const [user, setUser] = useState(null);
  const fetchUser = () => {
    fetch('/api/users/' + userId).then(res => res.json()).then(setUser);
  };
  useEffect(() => {
    fetchUser();
  }, []); // Missing fetchUser and userId
  return <div>{user?.name}</div>;
};
  `,
  'CleanComponent.tsx': `
import React from 'react';
import { useAuth } from '../hooks/useAuth';
export const Profile = () => {
  const { user } = useAuth();
  if (!user) return <Login />;
  return <ProfileCard user={user} />;
};
  `,
  'UselessMemo.tsx': `
import React, { useMemo } from 'react';
export const BadMemo = ({ name }) => {
  const greeting = useMemo(() => {
    return "Hello " + name; // Too cheap for memo
  }, [name]);
  return <div>{greeting}</div>;
};
  `,
  'GoodContext.tsx': `
import React, { createContext, useContext, useState } from 'react';
const ThemeContext = createContext('light');
export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('light');
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
};
export const useTheme = () => useContext(ThemeContext);
  `
};

for (const [filename, content] of Object.entries(files)) {
  fs.writeFileSync(path.join('data/test_files', filename), content.trim());
}
console.log('Created 10 test files.');
