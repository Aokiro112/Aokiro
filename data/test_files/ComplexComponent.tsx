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