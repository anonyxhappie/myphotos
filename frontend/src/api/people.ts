import type { TimelineResponse } from './types';

export interface PersonResponse {
  id: string;
  name: string;
  cover_media_id: string | null;
  face_count: number;
}

export async function fetchPeople(): Promise<PersonResponse[]> {
  const response = await fetch(`/api/people`);
  if (!response.ok) {
    throw new Error('Failed to fetch people');
  }
  return response.json();
}

export async function updatePersonName(personId: string, name: string): Promise<PersonResponse> {
  const response = await fetch(`/api/people/${personId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error('Failed to update person name');
  }
  return response.json();
}

export async function fetchPersonMedia(personId: string): Promise<TimelineResponse> {
  const response = await fetch(`/api/people/${personId}/media`);
  if (!response.ok) {
    throw new Error('Failed to fetch person media');
  }
  return response.json();
}

export async function fetchPets(): Promise<TimelineResponse> {
  const response = await fetch(`/api/pets`);
  if (!response.ok) {
    throw new Error('Failed to fetch pets');
  }
  return response.json();
}

export async function triggerClusterFaces(): Promise<{status: string, people_created: number}> {
  const response = await fetch(`/api/ml/cluster_faces`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to trigger clustering');
  }
  return response.json();
}

export async function bulkDeletePeoplePets(personIds: string[], deletePets: boolean): Promise<{status: string}> {
  const response = await fetch(`/api/people/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ person_ids: personIds, delete_pets: deletePets }),
  });
  if (!response.ok) {
    throw new Error('Failed to bulk delete people and pets');
  }
  return response.json();
}
