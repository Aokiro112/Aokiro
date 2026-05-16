import React, { useEffect } from 'react';
export const MemoryLeak = () => {
  useEffect(() => {
    window.addEventListener('resize', () => console.log('resize'));
    // Missing cleanup
  }, []);
  return <div>Leak</div>;
};