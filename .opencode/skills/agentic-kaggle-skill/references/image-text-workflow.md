# Image And Text Workflow

## Image Classification

Start with the data pipeline:

- Verify image paths, labels, EXIF/orientation, channel count, corrupted files, class balance, and duplicates.
- Split by subject, patient, scene, product, or source when repeated entities exist.
- Use stratification only after respecting groups.
- Resize consistently and record input resolution.
- Keep augmentations plausible for the domain.

Baseline:

- Use a pretrained backbone.
- Train with early stopping against the competition metric or a close surrogate.
- Save OOF probabilities and test probabilities.
- Add test-time augmentation only after the base model is stable.

Useful improvements:

- Class-balanced sampling or loss for imbalance.
- Mixup/cutmix when label semantics allow it.
- Resolution/model-family diversity for ensembles.
- Error analysis by class, source, brightness, resolution, and duplicate group.

## Segmentation

Validate masks before modeling:

- Check mask alignment, label values, missing masks, and dimensions.
- Match train-time loss to the metric: Dice, BCE+Dice, focal loss, IoU/Jaccard surrogate, or class-weighted losses.
- Split grouped images by subject/source.
- Tune postprocessing on OOF predictions only: thresholds, connected components, holes, minimum object size.

## Text Classification Or Regression

Keep two tracks: sparse classical models and neural/transformer models.

Sparse baseline:

- Minimal cleaning first; avoid destroying useful punctuation, casing, or domain tokens.
- Use word and character TF-IDF n-grams.
- Try logistic regression, linear SVM, ridge, naive Bayes variants, and SVD plus simple models.
- Use sparse matrices and save vectorizer settings.

Neural/transformer baseline:

- Split by source/author/user/question/product/prompt if duplication is possible.
- Validate tokenization, max length, truncation side, label encoding, and batch collation.
- Use pretrained models when the competition data is large enough or semantics matter.
- Compare speed and inference cost against simpler baselines; transformers are not automatically worth it.

Text features that often blend well:

- Text length, word count, sentence count, punctuation counts, capitalization ratios.
- Language/source/domain markers.
- SVD components from TF-IDF.
- Classical model probabilities as meta-features.

## Modality Mixing

For competitions with tabular plus text/image:

- Train each modality's strong baseline independently with the same fold IDs.
- Save OOF predictions per modality.
- Blend probabilities first; stack later if OOF coverage is clean.
- Add tabular metadata to neural models only after the single-modality baselines are trustworthy.
