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