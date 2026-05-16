import React, { createContext, useContext, useState } from 'react';
const ThemeContext = createContext('light');
export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('light');
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
};
export const useTheme = () => useContext(ThemeContext);