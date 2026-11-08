export type ImageFit = 'original' | 'portrait' | 'square' | 'landscape'

export async function preparePhoto(file: File, fit: ImageFit) {
  if (!['image/jpeg', 'image/jpg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Choose JPEG, PNG or WebP images.')
  if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name}: choose an original no larger than 20 MB.`)
  let image: ImageBitmap
  try { image = await createImageBitmap(file, { imageOrientation: 'from-image' }) }
  catch { throw new Error(`${file.name}: this browser could not open the image.`) }
  try {
    if (image.width * image.height > 25_000_000) throw new Error(`${file.name}: choose an image with no more than 25 megapixels.`)
    if (Math.min(image.width, image.height) < 320) throw new Error(`${file.name}: use at least 320 × 320 pixels.`)
    const ratio = image.width / image.height
    if (fit === 'original' && (ratio < 0.8 || ratio > 1.91)) throw new Error(`${file.name}: choose Portrait, Square or Landscape fit to add borders without cropping.`)
    const canvas = document.createElement('canvas')
    if (fit === 'original') {
      const scale = Math.min(1, 1440 / image.width, 1800 / image.height)
      canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale)
    } else {
      canvas.width = 1080; canvas.height = fit === 'portrait' ? 1350 : fit === 'square' ? 1080 : 566
    }
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Your browser could not prepare this image.')
    context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height)
    const scale = Math.min(canvas.width / image.width, canvas.height / image.height)
    const width = image.width * scale; const height = image.height * scale
    context.drawImage(image, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height)
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Could not prepare image.')), 'image/jpeg', 0.92))
    if (blob.size > 8 * 1024 * 1024) throw new Error('This image could not be prepared within Instagram’s publishing limit.')
    return { file: new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }), width: canvas.width, height: canvas.height }
  } finally { image.close() }
}
