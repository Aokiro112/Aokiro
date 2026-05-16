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