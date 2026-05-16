import React, { useMemo } from 'react';
export const BadMemo = ({ name }) => {
  const greeting = useMemo(() => {
    return "Hello " + name; // Too cheap for memo
  }, [name]);
  return <div>{greeting}</div>;
};