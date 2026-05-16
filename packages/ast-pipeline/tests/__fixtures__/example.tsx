import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Button } from './Button';

interface ExampleProps {
  title: string;
  onRefresh: () => void;
}

export const ExampleComponent: React.FC<ExampleProps> = ({ title, onRefresh }) => {
  const [count, setCount] = useState(0);
  const { user } = useAuth();

  useEffect(() => {
    console.log('Component mounted or count changed', count);
    return () => {
      console.log('Cleanup');
    };
  }, [count]);

  const handleRefresh = useCallback(() => {
    setCount(0);
    onRefresh();
  }, [onRefresh]);

  if (!user) return <div>Please log in</div>;

  return (
    <div className="example">
      <h1>{title}</h1>
      <p>Count: {count}</p>
      <Button onClick={() => setCount(c => c + 1)}>Increment</Button>
      <Button onClick={handleRefresh}>Refresh</Button>
    </div>
  );
};

export default ExampleComponent;
