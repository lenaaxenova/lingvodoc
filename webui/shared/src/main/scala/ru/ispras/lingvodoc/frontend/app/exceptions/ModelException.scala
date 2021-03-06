package ru.ispras.lingvodoc.frontend.app.exceptions


case class ModelException(message: String, nestedException: Throwable) extends  Exception(message, nestedException) {
  def this() = this("", null)
  def this(message: String) = this(message, null)
  def this(nestedException : Throwable) = this("", nestedException)
}
