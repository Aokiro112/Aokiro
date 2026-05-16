import React from 'react';
import { useAuth } from '../hooks/useAuth';
export const Profile = () => {
  const { user } = useAuth();
  if (!user) return <Login />;
  return <ProfileCard user={user} />;
};