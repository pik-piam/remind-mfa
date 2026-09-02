#!/usr/bin/env Rscript
#
# Generate REMIND-MFA input-data archives with mrmfa/madrat.
#
# Usage:
#   retrieve_mfa.R [--rev <revision>]
#                  [--dev <suffix>] [--sections steel,cement,plastic]
#                  [--no-source-docu] [--no-renv]
#
# The madrat folders are taken from the MADRAT_MAINFOLDER, MADRAT_CACHEFOLDER,
# MADRAT_OUTPUTFOLDER and MADRAT_PUCFOLDER environment variables, which madrat
# reads by itself.

library("mrmfa")

## configuration
cfg <- list()
cfg$model <- "MFA"

# Region mappings, addressed by the label that ends up in the archive name.
# The labels of the non-default mappings are registered with madrat below.
cfg$mappings <- c(
  h12 = "regionmappingH12.csv",
  eu21 = "regionmapping_21_EU11.csv",
  iso249 = "ISO_2_ISO.csv"
)
cfg$codeLabels <- c(eu21 = "2b1450bc", iso249 = "99727f0b")
# Current input data revision (<mainrevision>.<subrevision>)
cfg$revision <- "2.0.0"
# development suffix
cfg$dev <- ""
# sections of fullMFA to run (NULL: all of steel, cement, plastic)
cfg$runSections <- NULL
# whether to create source documentation files
cfg$withSourceDocu <- TRUE
# Use the default cache
cfg$cachetype <- "def"
# use renv by default
cfg$renv <- TRUE

## Command line options
argv <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(argv)) {
  arg <- argv[[i]]
  value <- function() {
    if (i + 1 > length(argv)) stop("Missing value for ", arg)
    argv[[i + 1]]
  }
  switch(arg,
    "--rev" = {
      cfg$revision <- value()
      i <- i + 1
    },
    "--dev" = {
      cfg$dev <- value()
      i <- i + 1
    },
    "--sections" = {
      cfg$runSections <- strsplit(value(), ",")[[1]]
      i <- i + 1
    },
    stop("Unknown argument: ", arg)
  )
  i <- i + 1
}


## helpers
add_source_docu_to_archive <- function(archive_path, regionmapping) {

  # produce source files for mrmfa (writes mrmfa_sources.* in the current wd)
  tryCatch(
    getSources_mrmfa(),
    error = function(e) message("getSources_mrmfa failed: ", e$message)
  )

  generated_files <- c("mrmfa_sources.csv", "mrmfa_sources.bib")
  generated_files <- generated_files[file.exists(generated_files)]

  if (length(generated_files) == 0) {
    message("No mrmfa source files found to add to archive.")
    return(invisible(NULL))
  }

  if (is.null(archive_path) || !file.exists(archive_path)) {
    return(invisible(NULL))
  }

  # extract archive into a temporary directory
  tmpdir <- tempfile("mfa-tar-")
  dir.create(tmpdir)

  if (system2("tar", c("-xzf", archive_path, "-C", tmpdir)) != 0) {
    warning("Failed to extract archive: ", archive_path)
    unlink(tmpdir, recursive = TRUE)
    return(invisible(NULL))
  }

  # copy generated files into temp tree
  file.copy(generated_files, tmpdir, overwrite = TRUE, copy.mode = TRUE)

  # move regionmapping file to regionmapping.csv
  file.rename(
    file.path(tmpdir, regionmapping),
    file.path(tmpdir, "regionmapping.csv")
  )

  # create new archive from temp tree then replace original
  tmparchive <- paste0(archive_path, ".tmp")
  if (system2("tar", c("-C", tmpdir, "-czf", tmparchive, ".")) != 0) {
    warning("Failed to create updated archive")
    unlink(tmpdir, recursive = TRUE)
    return(invisible(NULL))
  }

  if (!file.rename(tmparchive, archive_path)) {
    unlink(tmpdir, recursive = TRUE)
    stop("Failed to replace original archive")
  }

  unlink(tmpdir, recursive = TRUE)
  message("Added mrmfa source files to archive: ", archive_path)

  unlink(generated_files)

  invisible(NULL)
}

## Run
# getSources_mrmfa() writes into the working directory, which inside the
# container is the (possibly read-only) directory the user started from.
setwd(tempdir())

print("Config")
print(getConfig(verbose = TRUE, print = TRUE))
sessionInfo()

toolCodeLabels(add = cfg$codeLabels)

for (mappingFile in cfg$mappings) {
  archive_path <- retrieveData(
    model = cfg$model,
    regionmapping = mappingFile,
    runSections = cfg$runSections,
    rev = cfg$revision,
    dev = cfg$dev,
    cachetype = cfg$cachetype,
    renv = cfg$renv
  )

  if (cfg$withSourceDocu) {
    add_source_docu_to_archive(archive_path, mappingFile)
  }
}
