import { useEffect, useState } from 'react';
import { api, auth } from '../api/client';

export default function useProfilePicture() {
  const user = auth.snapshot().user;
  const revision = user?.profile_photo_revision;
  const key = revision ? `${user.id}:${revision}` : null;
  const [picture, setPicture] = useState(null);

  useEffect(() => {
    if (!key) return undefined;
    let active = true;
    let url;
    api.get('/account/profile/photo?' + new URLSearchParams({ revision })).then(response => response.clone().blob()).then(blob => {
      if (!active) return;
      url = URL.createObjectURL(blob);
      setPicture({ key, url });
    }).catch(() => {
      // Keep the initials visible if an image is unavailable.
    });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [key, revision]);

  return picture?.key === key ? picture.url : null;
}
