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