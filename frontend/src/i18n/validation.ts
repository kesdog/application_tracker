import { locale, t } from './index'

/** Native validation otherwise follows the browser's installed language. */
export function localizeValidation(element: EventTarget | null): void {
  if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)) return
  element.setCustomValidity('')
  if (locale.value !== 'fr' || element.validity.valid) return
  const state = element.validity
  let message = t('Please enter a valid value.')
  if (state.valueMissing) message = t('Please fill in this field.')
  else if (element instanceof HTMLInputElement) {
    if (state.typeMismatch && element.type === 'email') message = t('Please enter a valid email address.')
    else if (state.typeMismatch && element.type === 'url') message = t('Please enter a valid URL.')
    else if (state.rangeUnderflow) message = t('Please enter a value of at least {p0}.', { p0: element.min })
    else if (state.rangeOverflow) message = t('Please enter a value no greater than {p0}.', { p0: element.max })
  }
  element.setCustomValidity(message)
}

export function installValidationLocale(): void {
  document.addEventListener('invalid', event => localizeValidation(event.target), true)
  document.addEventListener('input', event => {
    const element = event.target
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) element.setCustomValidity('')
  }, true)
}
