import { defaultAppearance, type AppearanceSettings } from './appearanceDefaults'

export const appearancePresets = [
  { id: 'default', label: 'Default', colors: { ...defaultAppearance } },
  { id: 'dark', label: 'Dark', colors: {
    ...defaultAppearance,
    primary: '#c3b2ff', primaryHover: '#dbceff', link: '#8fe3dd', focus: '#b4caff',
    background: '#0c1222', surface: '#17213a', surfaceMuted: '#25324d', border: '#647698',
    text: '#f0f3ff', textMuted: '#b9c5df',
    submitted: '#9ecbff', interview: '#d2b4f0', successful: '#8fd4ad', unsuccessful: '#ffacb0',
    withdrawn: '#bac5d2', cancelled: '#f0c28b', ghosted: '#b9c2cf',
    overdue: '#ffacb0', dueSoon: '#f0c28b', live: '#8fd4ad', postingClosed: '#bac5d2',
  } },
  { id: 'high-contrast', label: 'High Contrast', colors: {
    ...defaultAppearance,
    primary: '#000000', primaryHover: '#202020', link: '#003399', focus: '#003399',
    background: '#ffffff', surface: '#ffffff', surfaceMuted: '#eeeeee', border: '#000000',
    text: '#000000', textMuted: '#333333',
    submitted: '#003399', interview: '#551177', successful: '#005522', unsuccessful: '#990000',
    withdrawn: '#333333', cancelled: '#663300', ghosted: '#444444',
    overdue: '#990000', dueSoon: '#663300', live: '#005522', postingClosed: '#333333',
  } },
  { id: 'soft', label: 'Soft', colors: {
    ...defaultAppearance,
    primary: '#514770', primaryHover: '#403658', link: '#59467e', focus: '#745e9c',
    background: '#f7f5f9', surface: '#ffffff', surfaceMuted: '#eeebf3', border: '#c9c2d5',
    text: '#302b3c', textMuted: '#635b70',
  } },
  { id: 'minimal', label: 'Minimal', colors: {
    ...defaultAppearance,
    primary: '#333333', primaryHover: '#171717', link: '#333333', focus: '#555555',
    background: '#fafafa', surface: '#ffffff', surfaceMuted: '#f0f0f0', border: '#cccccc',
    text: '#222222', textMuted: '#595959',
  } },
] satisfies { id: string; label: string; colors: AppearanceSettings }[]

export type AppearancePresetId = typeof appearancePresets[number]['id']
