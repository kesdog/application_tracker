import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

const variable = (name: string) => `var(--at-${name})`
const secondaryControl = { background: variable('surface-muted'), hoverBackground: variable('surface-muted'), activeBackground: variable('surface-muted'), color: variable('text'), hoverColor: variable('text'), activeColor: variable('text') }
const overlayColors = { background: variable('surface'), borderColor: variable('border'), color: variable('text') }
export const trackerPreset = definePreset(Aura, {
  semantic: {
    disabledOpacity: '1',
    primary: {
      color: variable('primary'), contrastColor: variable('primary-contrast'),
      hoverColor: variable('primary-hover'), activeColor: variable('primary-hover'),
    },
    surface: {
      0: variable('surface'), 50: variable('background'), 100: variable('surface-muted'),
      200: variable('border'), 300: variable('border'), 400: variable('text-muted'),
      500: variable('text-muted'), 600: variable('text-muted'), 700: variable('text'),
      800: variable('text'), 900: variable('surface'), 950: variable('surface'),
    },
    focusRing: { width: '3px', color: variable('focus') },
    text: { color: variable('text'), hoverColor: variable('text'), mutedColor: variable('text-muted'), hoverMutedColor: variable('text') },
    formField: {
      background: variable('surface'), color: variable('text'), borderColor: variable('border'),
      placeholderColor: variable('text-muted'), disabledBackground: variable('surface-muted'),
      disabledColor: variable('text-muted'),
      invalidBorderColor: variable('unsuccessful'), invalidPlaceholderColor: variable('unsuccessful'),
      focusRing: { width: '3px', style: 'solid', color: variable('focus'), offset: '2px' },
    },
    content: { background: variable('surface'), hoverBackground: variable('surface-muted'), borderColor: variable('border'), color: variable('text'), hoverColor: variable('text') },
    highlight: { background: variable('surface-muted'), focusBackground: variable('surface-muted'), color: variable('text'), focusColor: variable('text') },
    list: { option: { focusBackground: variable('surface-muted'), focusColor: variable('text'), selectedBackground: variable('surface-muted'), selectedColor: variable('text'), selectedFocusBackground: variable('surface-muted'), selectedFocusColor: variable('text') } },
    overlay: { select: overlayColors, popover: overlayColors, modal: overlayColors },
  },
  components: {
    button: { root: {
      primary: { background: variable('primary'), hoverBackground: variable('primary-hover'), activeBackground: variable('primary-hover'), borderColor: variable('primary'), hoverBorderColor: variable('primary-hover'), activeBorderColor: variable('primary-hover'), color: variable('primary-contrast'), hoverColor: variable('primary-hover-contrast'), activeColor: variable('primary-hover-contrast') },
      danger: { background: variable('unsuccessful'), hoverBackground: variable('unsuccessful'), activeBackground: variable('unsuccessful'), borderColor: variable('unsuccessful'), hoverBorderColor: variable('unsuccessful'), activeBorderColor: variable('unsuccessful'), color: variable('unsuccessful-contrast'), hoverColor: variable('unsuccessful-contrast'), activeColor: variable('unsuccessful-contrast') },
      secondary: { background: variable('surface-muted'), hoverBackground: variable('surface-muted'), activeBackground: variable('surface-muted'), borderColor: variable('border'), hoverBorderColor: variable('border'), activeBorderColor: variable('border'), color: variable('text'), hoverColor: variable('text'), activeColor: variable('text') },
    }, outlined: {
      secondary: { color: variable('text'), borderColor: variable('border'), hoverBackground: variable('surface-muted'), activeBackground: variable('surface-muted') },
      danger: { color: variable('unsuccessful'), borderColor: variable('unsuccessful'), hoverBackground: variable('surface-muted'), activeBackground: variable('surface-muted') },
    }, text: { secondary: { color: variable('text'), hoverBackground: variable('surface-muted'), activeBackground: variable('surface-muted') } } },
    togglebutton: {
      root: { background: variable('surface-muted'), hoverBackground: variable('surface-muted'), color: variable('text-muted'), hoverColor: variable('text'), borderColor: variable('border'), checkedBackground: variable('primary'), checkedBorderColor: variable('primary'), checkedColor: variable('primary-contrast') },
      content: { checkedBackground: variable('primary') },
    },
    autocomplete: { dropdown: secondaryControl },
    datepicker: { dropdown: secondaryControl, today: { background: variable('surface-muted'), color: variable('text') } },
    chip: { root: { background: variable('surface-muted'), focusBackground: variable('surface-muted'), color: variable('text') }, icon: { color: variable('text-muted') }, removeIcon: { color: variable('text-muted') } },
    datatable: { root: { borderColor: variable('border') }, headerCell: { background: variable('surface-muted'), color: variable('text-muted') } },
  },
})
