import React from 'react';
import { GrandChild } from './GrandChild';
export const Parent = ({ user, theme, onUpdate, settings, features }) => {
  return (
    <div>
      <Child user={user} theme={theme} onUpdate={onUpdate} settings={settings} features={features} />
    </div>
  );
};